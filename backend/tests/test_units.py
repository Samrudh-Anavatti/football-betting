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
