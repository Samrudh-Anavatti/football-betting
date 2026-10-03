"""End-to-end: sync → odds → match bundle → tip → result → settled record."""
from .conftest import KICKOFF, af_fixture

API = "/api/v1"


def test_admin_requires_login(client):
    assert client.get(f"{API}/admin/integrations").status_code == 401


def test_full_flow(client, auth, fake):
    # Quota check uses the free status endpoints.
    q = client.post(f"{API}/admin/integrations/api_football/check", headers=auth).json()
    assert q["remaining"] == 90 and q["plan"] == "Free"

    run = client.post(f"{API}/admin/sync/fixtures", json={"league_ids": [39]}, headers=auth).json()
    assert run["status"] == "ok" and run["requests_made"] == 2 and run["items"] == 2

    run = client.post(f"{API}/admin/sync/odds", json={"league_ids": [39], "markets": ["h2h", "totals"]}, headers=auth).json()
    assert run["status"] == "ok", run
    assert run["credits_used"] == 2 and run["details"]["leagues"]["Premier League"]["matched"] == 1

    fixtures = client.get(f"{API}/fixtures").json()
    assert fixtures[0]["best_1x2"] == {"home": 1.45, "away": 7.5, "draw": 5.0}

    run = client.post(f"{API}/admin/matches/1001/context", headers=auth).json()
    assert run["status"] == "ok" and run["requests_made"] == 4 + 2  # +2: early-season form top-up

    m = client.get(f"{API}/matches/1001").json()
    one_x_two = m["odds"]["markets"][0]
    assert one_x_two["market"] == "1X2" and one_x_two["selections"][0]["best_bookmaker"] == "Sky Bet"
    assert m["context"]["h2h"][0]["hg"] == 1 and m["context"]["injuries"][0]["player"] == "R. Dias"
    assert len(m["standings"]["rows"]) == 2

    tip = client.post(f"{API}/admin/tips", headers=auth, json={
        "fixture_id": 1001, "market": "OU", "selection": "over", "line": 2.5, "odds": 1.6,
        "bookmaker": "William Hill", "stake_units": 2, "reasoning": "Both leaky",
    })
    assert tip.status_code == 201, tip.text
    client.post(f"{API}/admin/bets", headers=auth, json={
        "fixture_id": 1001, "market": "OU", "selection": "over", "line": 2.5, "odds": 1.6, "stake": 50,
    })
    assert len(client.get(f"{API}/tips").json()) == 1

    # Match finishes 3-1 → next fixtures sync settles everything.
    fake.af_fixtures = [af_fixture(1001, (50, "Manchester City"), (39, "Wolves"), KICKOFF, "FT", 3, 1)]
    client.post(f"{API}/admin/sync/fixtures", json={"league_ids": [39], "include_standings": False}, headers=auth)

    rec = client.get(f"{API}/record").json()
    assert rec["won"] == 1 and rec["profit_units"] == 1.2 and rec["roi"] == 0.6
    acc = client.get(f"{API}/admin/accounts", headers=auth).json()["accounts"]
    ivo = next(a for a in acc if a["username"] == "ivo")
    assert ivo["profit"] == 30 and ivo["balance"] == 1030

    integ = client.get(f"{API}/admin/integrations", headers=auth).json()
    odds = next(p for p in integ["providers"] if p["key"] == "odds_api")
    assert odds["quota"]["remaining"] == 480 and odds["quota"]["limit"] == 500


def test_surfaces_provider_errors(client, auth, fake, monkeypatch):
    import httpx

    def broken(request):
        return httpx.Response(200, json={"errors": {"plan": "Free plans do not have access to this season"}, "response": []})

    from app.providers.api_football import ApiFootball
    from app.services import sync
    monkeypatch.setattr(sync, "make_api_football", lambda: ApiFootball("k", 0, transport=httpx.MockTransport(broken)))
    run = client.post(f"{API}/admin/sync/fixtures", json={"league_ids": [61]}, headers=auth).json()
    assert run["status"] == "error" and "do not have access" in run["message"]
    lg = next(lg for lg in client.get(f"{API}/leagues").json() if lg["id"] == 61)
    assert "do not have access" in lg["last_error"]
