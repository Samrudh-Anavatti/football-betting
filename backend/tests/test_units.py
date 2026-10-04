from datetime import datetime, timedelta
from types import SimpleNamespace as NS

from app.services.matching import best_fixture_for_event, name_similarity
from app.services.settlement import outcome, profit_for


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
