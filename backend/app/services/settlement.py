"""Settle tips and bets from final scores (90 minutes, like the bookies do)."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Bet, Fixture, Tip

FINISHED = {"FT", "AET", "PEN"}
VOIDED = {"PST", "CANC", "ABD", "AWD", "WO"}

MARKETS = {
    "1X2": ["home", "draw", "away"],
    "OU": ["over", "under"],
    "BTTS": ["yes", "no"],
}


def outcome(market: str, selection: str, line: float | None, home: int, away: int) -> str | None:
    """'won' | 'lost' | 'void', or None when we can't settle automatically."""
    if market == "1X2":
        actual = "home" if home > away else "away" if away > home else "draw"
        return "won" if selection == actual else "lost"
    if market == "BTTS":
        both = home > 0 and away > 0
        return "won" if (selection == "yes") == both else "lost"
    if market == "OU" and line is not None:
        if line * 4 % 2 == 1:  # quarter lines (2.25, 2.75) → settle by hand
            return None
        total = home + away
        if total == line:
            return "void"
        over = total > line
        return "won" if (selection == "over") == over else "lost"
    return None


def profit_for(status: str, stake: float, odds: float) -> float:
    if status == "won":
        return round(stake * (odds - 1), 2)
    if status == "lost":
        return -stake
    return 0.0


def apply_result(obj, status: str, stake: float) -> None:
    obj.status = status
    obj.settled_at = datetime.utcnow()
    profit = profit_for(status, stake, obj.odds)
    if isinstance(obj, Tip):
        obj.profit_units = profit
    else:
        obj.profit = profit


def settle_fixture(db: Session, fx: Fixture) -> int:
    """Settle pending tips/bets on a fixture. Returns how many were settled."""
    if fx.status in VOIDED:
        result_for = lambda m, s, l: "void"  # noqa: E731
    elif fx.status in FINISHED and fx.home_goals is not None and fx.away_goals is not None:
        result_for = lambda m, s, l: outcome(m, s, l, fx.home_goals, fx.away_goals)  # noqa: E731
    else:
        return 0
    n = 0
    for tip in db.scalars(select(Tip).where(Tip.fixture_id == fx.id, Tip.status == "pending")):
        if (res := result_for(tip.market, tip.selection, tip.line)) is not None:
            apply_result(tip, res, tip.stake_units)
            n += 1
    for bet in db.scalars(select(Bet).where(Bet.fixture_id == fx.id, Bet.status == "pending")):
        if (res := result_for(bet.market, bet.selection, bet.line)) is not None:
            apply_result(bet, res, bet.stake)
            n += 1
    return n
