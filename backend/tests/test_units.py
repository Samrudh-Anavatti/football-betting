from datetime import datetime, timedelta
from types import SimpleNamespace as NS

from app.services.matching import best_fixture_for_event, name_similarity
from app.services.markets import build_markets, parse_value, to_code
from app.services.settlement import market_outcome, outcome, profit_for


def test_name_similarity_handles_provider_spellings():
    assert name_similarity("Wolves", "Wolverhampton Wanderers") == 1.0
    assert name_similarity("Bayern München", "Bayern Munich") == 1.0
    assert name_similarity("FC Barcelona", "Barcelona") == 1.0
    assert name_similarity("Inter", "Inter Milan") == 1.0
    assert name_similarity("Sporting Lisbon", "Sporting CP") == 1.0
    assert name_similarity("Arsenal", "Chelsea") < 0.5


def test_event_matching_respects_kickoff_window():
    ko = datetime(2026, 10, 4, 14)
    fx = NS(kickoff=ko, home_team=NS(name="Manchester City"), away_team=NS(name="Wolves"))
    assert best_fixture_for_event("Manchester City", "Wolverhampton Wanderers", ko, [fx])[0] is fx
    assert best_fixture_for_event("Manchester City", "Wolverhampton Wanderers", ko + timedelta(days=1), [fx])[0] is None


def test_outcomes():
    assert outcome("1X2", "home", None, 2, 1) == "won"
    assert outcome("1X2", "draw", None, 2, 1) == "lost"
    assert outcome("BTTS", "yes", None, 1, 1) == "won"
    assert outcome("OU", "over", 2.5, 2, 1) == "won"
    assert outcome("OU", "under", 3.0, 2, 1) == "void"
    assert outcome("OU", "over", 2.25, 2, 1) is None  # quarter line → manual


def test_profit():
    assert profit_for("won", 10, 2.5) == 15
    assert profit_for("lost", 10, 2.5) == -10
    assert profit_for("void", 10, 2.5) == 0


def test_market_outcomes():
    # 2-1 full time, 1-1 at half time
    assert market_outcome("Double Chance", "Home/Draw", 2, 1, 1, 1) == "won"
    assert market_outcome("Home/Away", "Home", 1, 1, 0, 0) == "void"
    assert market_outcome("Exact Score", "2:1", 2, 1, 1, 1) == "won"
    assert market_outcome("HT/FT Double", "Draw/Home", 2, 1, 1, 1) == "won"
    assert market_outcome("Second Half Winner", "Home", 2, 1, 1, 1) == "won"
    assert market_outcome("Total - Away", "Over 0.5", 2, 1, 1, 1) == "won"
    assert market_outcome("Result/Total Goals", "Home/Under 3.5", 2, 1, 1, 1) == "won"
    assert market_outcome("Total Goals/Both Teams To Score", "o/yes 2.5", 2, 1, 1, 1) == "won"
    assert market_outcome("First Half Winner", "Home", 2, 1, None, None) is None  # no half-time score
    assert market_outcome("Anytime Goal Scorer", "Haaland", 2, 1, 1, 1) is None  # by hand


def test_handicap_and_team_goal_outcomes():
    # Rizespor 0-3 Fenerbahçe, Lazio 3-1 Monza: the two picks that sat pending
    assert market_outcome("Home Team Score a Goal", "No", 0, 3, 0, 1) == "won"
    assert market_outcome("Handicap Result", "Home -1", 3, 1, 1, 0) == "won"
    # Handicap lines are the home team's, whichever side is picked
    assert market_outcome("Handicap Result", "Draw -1", 2, 1, 1, 0) == "won"
    assert market_outcome("Handicap Result", "Away -1", 2, 1, 1, 0) == "lost"
    assert market_outcome("Handicap Result", "Away +1", 0, 2, 0, 0) == "won"
    assert market_outcome("Asian Handicap", "Away -1.5", 2, 1, 1, 1) == "won"  # away +1.5
    assert market_outcome("Asian Handicap", "Home -1", 2, 1, 1, 1) == "void"
    assert market_outcome("Asian Handicap", "Home -0.75", 2, 1, 1, 1) is None  # quarter line, by hand
    assert market_outcome("Handicap Result - First Half", "Home -1", 2, 1, 1, 0) == "lost"
    assert market_outcome("Away Team Score a Goal (2nd Half)", "Yes", 2, 1, 1, 1) == "lost"
    assert market_outcome("Winning Margin", "1 by 1", 2, 1, 1, 1) == "won"
    assert market_outcome("Winning Margin", "2 by 4+", 0, 5, 0, 1) == "won"
    assert market_outcome("Winning Margin", "Draw", 1, 1, 0, 0) == "lost"
    assert market_outcome("Number Of Goals In Match", "2 or 3 goals", 2, 1, 1, 1) == "won"
    assert market_outcome("Exact Goals Number", "more 4", 3, 2, 1, 1) == "won"
    assert market_outcome("Second Half Exact Goals Number", "1", 2, 1, 1, 1) == "won"
    # San Marino 0-2 Belarus: only one side scored, so first and last scorer are known; 2-1 needs the timeline.
    assert market_outcome("Team To Score First", "Away", 0, 2, 0, 1) == "won"
    assert market_outcome("Team To Score Last", "Home", 0, 2, 0, 1) == "lost"
    assert market_outcome("Team To Score First", "No goal", 0, 0, 0, 0) == "won"
    assert market_outcome("Team To Score First", "Home", 2, 1, 1, 1) is None


def test_value_parsing_and_codes():
    assert parse_value("Over 2.5") == ("Over", 2.5)
    assert parse_value("Home -1.25") == ("Home", -1.25)
    assert parse_value("2:1") == ("2:1", None)
    assert to_code(1, "Draw") == ("1X2", "draw", None)
    assert to_code(5, "Under 3.5") == ("OU", "under", 3.5)
    assert to_code(12, "Home/Draw") is None


def test_fair_price_needs_a_complete_book():
    books = [{"id": 8, "name": "A", "bets": [
        {"id": 1, "name": "Match Winner", "values": [{"value": "Home", "odd": "2.0"}, {"value": "Draw", "odd": "3.5"},
                                                      {"value": "Away", "odd": "4.0"}]},
        {"id": 92, "name": "Anytime Goal Scorer", "values": [{"value": f"P{i}", "odd": "2.5"} for i in range(12)]},
    ]}]
    mk = {m["id"]: m for m in build_markets(books)}
    sels = mk[1]["groups"][0]["selections"]
    assert all(s["fair"] for s in sels) and abs(sum(s["prob"] for s in sels) - 1) < 0.01
    assert mk[92]["layout"] == "list" and mk[92]["category"] == "players"
    assert all(s["fair"] is None for s in mk[92]["groups"][0]["selections"])  # not mutually exclusive


def test_board_is_stored_again_when_the_bookmakers_change(client, monkeypatch):
    """Same prices from API-Football, but a different set of our bookmakers: the stored board follows the set."""
    import json
    from datetime import datetime, timedelta

    from app import config
    from app.database import SessionLocal
    from app.models import Fixture, League, MarketBook, OddsSnapshot, Team
    from app.services import sync

    now, fid = datetime(2026, 1, 1, 12), 990001
    bets = [{"id": 1, "name": "Match Winner", "values": [{"value": "Home", "odd": "2.00"}]}]
    item = {"fixture": {"id": fid}, "update": "2026-01-01T10:00:00+00:00", "bookmakers": [
        {"id": 8, "name": "Bet365", "bets": bets}, {"id": 4, "name": "Pinnacle", "bets": bets},
        {"id": 32, "name": "Betano", "bets": bets}]}
    names = lambda db: db.flush() or [b["name"] for b in json.loads(db.get(MarketBook, fid).bookmakers_json)]
    with SessionLocal() as db:
        lg = db.scalars(__import__("sqlalchemy").select(League)).first()
        db.add_all([Team(id=fid, name="Home"), Team(id=fid + 1, name="Away")])
        db.add(Fixture(id=fid, league_id=lg.id, season=lg.season, kickoff=now + timedelta(days=1), status="NS",
                       home_team_id=fid, away_team_id=fid + 1))
        db.flush()
        try:
            monkeypatch.setattr(config, "ODDS_BOOKMAKERS", [8, 4])
            sync.ingest_market_items(db, [item], now)
            assert names(db) == ["Bet365", "Pinnacle"]
            monkeypatch.setattr(config, "ODDS_BOOKMAKERS", [8, 32])
            sync.ingest_market_items(db, [item], now + timedelta(hours=1))
            assert names(db) == ["Bet365", "Betano"]
            rows = db.query(OddsSnapshot).filter_by(fixture_id=fid).count()
            sync.ingest_market_items(db, [item], now + timedelta(hours=2))  # nothing changed: no new history
            assert db.query(OddsSnapshot).filter_by(fixture_id=fid).count() == rows
        finally:
            db.rollback()


def test_quarter_lines_settle_when_both_halves_agree():
    """Under 4.25 is half on Under 4 and half on Under 4.5: one goal wins both, four goals wins one and pushes one."""
    from app.services.settlement import market_outcome as out

    assert out("Goal Line", "Under 4.25", 1, 0, 0, 0) == "won"
    assert out("Goal Line", "Under 4.25", 3, 2, 0, 0) == "lost"
    assert out("Goal Line", "Under 4.25", 2, 2, 0, 0) is None  # half win: by hand
    assert out("Goal Line", "Over 2.75", 2, 2, 0, 0) == "won"
    assert out("Goal Line", "Over 2.75", 2, 1, 0, 0) is None  # half loss: by hand
    assert out("Goal Line", "Over 2.75", 1, 1, 0, 0) == "lost"
    assert out("Asian Handicap", "Home -0.25", 2, 0, 0, 0) == "won"
    assert out("Asian Handicap", "Home -0.25", 1, 1, 0, 0) is None  # half loss: by hand
    assert out("Asian Handicap", "Away +0.75", 3, 0, 0, 0) == "lost"
    assert out("Asian Handicap", "Away -0.25", 1, 1, 0, 0) is None  # the line is the home team's: half win, by hand
