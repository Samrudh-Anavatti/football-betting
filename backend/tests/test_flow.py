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
    assert run["status"] == "ok" and run["requests_made"] == 8 + 2  # +2: early-season form top-up; 8 includes the previous XI

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


def test_pitch_card_previous_then_confirmed_xi(client, auth, fake):
    from app.services.sync import fix_text

    assert fix_text("Gabriel MagalhÃ£es") == "Gabriel Magalhães"
    assert fix_text("Oâ€™Neill") == "O’Neill"
    assert fix_text("Fenerbahçe") == "Fenerbahçe"  # already right: unchanged

    client.post(f"{API}/admin/sync/fixtures", json={"league_ids": [39]}, headers=auth)
    client.post(f"{API}/admin/matches/1001/context", headers=auth)
    m = client.get(f"{API}/matches/1001").json()
    assert [i["player"] for i in m["context"]["injuries"]] == ["R. Dias"]  # duplicate dropped
    home, away = m["pitch"]["home"], m["pitch"]["away"]
    # City's previous match was fixture 1000; the fake has line-ups for City only.
    assert home["source"] == "previous" and home["previous_match"]["opponent"] == "Wolves"
    assert home["start_xi"][0] == {"id": 1, "name": "Haaland", "number": 9, "pos": "F", "grid": "4:2"}
    assert home["substitutes"][0]["name"] == "Gabriel Magalhães"
    assert home["transfermarkt"].endswith("/manchester-city/startseite/verein/281")
    assert away["source"] is None and away["transfermarkt"].endswith("schnellsuche?query=Wolves")  # not in the map
    calls = fake.calls.count("/fixtures/lineups")

    client.post(f"{API}/admin/matches/1001/context", headers=auth)
    assert fake.calls.count("/fixtures/lineups") == calls  # a finished match's XI is fetched once

    client.post(f"{API}/admin/matches/1001/lineups", headers=auth)
    assert client.get(f"{API}/matches/1001").json()["pitch"]["home"]["source"] == "confirmed"


def test_closing_price_is_stored_once_the_match_starts(client, auth):
    import json
    from datetime import datetime, timedelta

    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import Fixture, MarketBook, Team, Tip, User
    from app.services.settlement import settle_pending

    now = datetime.utcnow()
    db = SessionLocal()
    db.merge(Team(id=901, name="Home FC"))
    db.merge(Team(id=902, name="Away FC"))
    db.add(Fixture(id=9001, league_id=39, season=2026, kickoff=now - timedelta(hours=1), status="1H",
                   home_team_id=901, away_team_id=902))
    db.flush()
    book = [{"id": 8, "name": "Bet365", "bets": [{"id": 1, "name": "Match Winner", "values": [
        {"value": "Home", "odd": "1.80"}, {"value": "Draw", "odd": "3.6"}, {"value": "Away", "odd": "4.5"}]}]}]
    db.add(MarketBook(fixture_id=9001, pulled_at=now - timedelta(hours=2), bookmakers_json=json.dumps(book)))
    ivo = db.scalar(select(User).where(User.username == "ivo"))
    db.add(Tip(id=9001, fixture_id=9001, author_id=ivo.id, market_id=1, market="Match Winner", selection="Home",
               odds=2.0, created_at=now - timedelta(hours=3)))
    db.commit()

    settle_pending(db)  # startup backfill: the match has kicked off, so its closing price is final
    tip = db.get(Tip, 9001)
    assert tip.closing_odds == 1.8 and tip.closing_checked_at is not None
    db.get(MarketBook, 9001).bookmakers_json = "[]"  # the record no longer reads the book
    db.commit()
    try:
        assert client.get(f"{API}/record").json()["clv_samples"] >= 1
    finally:  # an in-play match would show up in the scheduler tests' live-scores job
        for row in (db.get(Tip, 9001), db.get(MarketBook, 9001)):
            db.delete(row)
        db.flush()
        db.delete(db.get(Fixture, 9001))
        db.commit()
        db.close()
