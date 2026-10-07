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
    assert run["status"] == "ok" and run["requests_made"] == 7 + 2  # +2: early-season form top-up

    # Before an API-Football pull the board falls back to The Odds API's snapshots.
    m = client.get(f"{API}/matches/1001").json()
    assert m["odds"]["source"] == "odds_api"
    one_x_two = m["odds"]["markets"][0]
    assert one_x_two["name"] == "Match Winner" and one_x_two["groups"][0]["selections"][0]["best_bookmaker"] == "Sky Bet"
    assert m["context"]["prediction"]["winner"] == "Manchester City" and m["context"]["home_stats"]["form"] == "WWDLW"
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


def test_markets_board_and_any_market_pick(client, auth, fake):
    client.post(f"{API}/admin/sync/fixtures", json={"league_ids": [39]}, headers=auth)
    run = client.post(f"{API}/admin/sync/markets", json={"league_ids": [39]}, headers=auth).json()
    assert run["status"] == "ok" and run["items"] == 1 and run["requests_made"] == 1

    m = client.get(f"{API}/matches/1001").json()
    board = m["odds"]
    assert board["source"] == "api_football"
    assert board["bookmakers"] == ["Bet365", "William Hill"]  # 1xBet isn't one of ours
    cats = {c["key"] for c in board["categories"]}
    assert {"main", "cards"} <= cats
    result = next(mk for mk in board["markets"] if mk["id"] == 1)
    home = result["groups"][0]["selections"][0]
    assert home["value"] == "Home" and home["best"] == 1.45 and home["best_bookmaker"] == "William Hill"
    assert home["prices"] == [1.4, 1.45] and home["fair"] is not None
    goals = next(mk for mk in board["markets"] if mk["id"] == 5)
    assert goals["layout"] == "lines" and goals["main_line"] == 2.5
    # Core markets also land in the fixture list's best prices.
    assert client.get(f"{API}/fixtures").json()[0]["best_1x2"]["home"] == 1.45

    # A board pick on a core market is stored as our short code...
    t1 = client.post(f"{API}/admin/tips", headers=auth, json={
        "fixture_id": 1001, "market_id": 1, "market": "Match Winner", "selection": "Home", "odds": 1.45})
    assert t1.status_code == 201 and t1.json()["market"] == "1X2" and t1.json()["selection"] == "home"
    # ...anything else keeps API-Football's names.
    t2 = client.post(f"{API}/admin/tips", headers=auth, json={
        "fixture_id": 1001, "market_id": 12, "market": "Double Chance", "selection": "Home/Draw", "odds": 1.10})
    t3 = client.post(f"{API}/admin/tips", headers=auth, json={
        "fixture_id": 1001, "market_id": 80, "market": "Cards Over/Under", "selection": "Over 3.5", "odds": 1.9})
    assert t2.json()["market_id"] == 12 and t3.json()["line"] == 3.5

    fake.af_fixtures = [af_fixture(1001, (50, "Manchester City"), (39, "Wolves"), KICKOFF, "FT", 1, 1)]
    client.post(f"{API}/admin/sync/fixtures", json={"league_ids": [39], "include_standings": False}, headers=auth)
    by_id = {t["id"]: t for t in client.get(f"{API}/admin/tips", headers=auth).json()["tips"]}
    assert by_id[t1.json()["id"]]["status"] == "lost"
    assert by_id[t2.json()["id"]]["status"] == "won"  # Double chance Home/Draw on a 1-1
    assert by_id[t3.json()["id"]]["status"] == "pending"  # cards: settled by hand


def test_lineups(client, auth, fake):
    client.post(f"{API}/admin/sync/fixtures", json={"league_ids": [39]}, headers=auth)
    run = client.post(f"{API}/admin/matches/1001/lineups", headers=auth).json()
    assert run["status"] == "ok"
    assert client.get(f"{API}/matches/1001").json()["context"]["lineups"][0]["start_xi"] == ["Haaland (F)"]
