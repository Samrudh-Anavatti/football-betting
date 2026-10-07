"""Settle tips and bets from final scores (90 minutes, like the bookies do).

Two vocabularies: our short codes (1X2/OU/BTTS) and API-Football market names
for everything else on the board. Anything that needs more than the full-time
and half-time scores (scorers, corners, cards, Asian quarter lines...) returns
None and is settled by hand in Admin, Picks.
"""
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


def _res(h: int, a: int) -> str:
    return "Home" if h > a else "Away" if a > h else "Draw"


def _ou(total: int, side: str, line: float | None) -> str | None:
    if line is None or side not in ("Over", "Under") or line * 4 % 2 == 1:
        return None
    if total == line:
        return "void"
    return "won" if (side == "Over") == (total > line) else "lost"


def _yn(value: str, truth: bool) -> str | None:
    if value not in ("Yes", "No"):
        return None
    return "won" if (value == "Yes") == truth else "lost"


def _wl(ok: bool) -> str:
    return "won" if ok else "lost"


def _score(v: str) -> tuple[int, int] | None:
    try:
        h, a = v.split(":")
        return int(h), int(a)
    except ValueError:
        return None


def market_outcome(market: str, value: str, h: int, a: int, hh: int | None, ha: int | None) -> str | None:
    """Settle an API-Football market by name. hh/ha = half-time score (may be unknown)."""
    from .markets import parse_value

    v = value.strip()
    side, line = parse_value(v)
    total = h + a
    have_ht = hh is not None and ha is not None
    sh, sa = (h - hh, a - ha) if have_ht else (None, None)  # second half

    full = {
        "Match Winner": lambda: _wl(v == _res(h, a)),
        "Home/Away": lambda: "void" if h == a else _wl(v == _res(h, a)),
        "Double Chance": lambda: _wl(_res(h, a) in v.split("/")) if "/" in v else None,
        "Goals Over/Under": lambda: _ou(total, side, line),
        "Total - Home": lambda: _ou(h, side, line),
        "Total - Away": lambda: _ou(a, side, line),
        "Both Teams Score": lambda: _yn(v, h > 0 and a > 0),
        "Exact Score": lambda: _wl(_score(v) == (h, a)) if _score(v) else None,
        "Clean Sheet - Home": lambda: _yn(v, a == 0),
        "Clean Sheet - Away": lambda: _yn(v, h == 0),
        "Win To Nil": lambda: _wl((v == "Home" and h > a and a == 0) or (v == "Away" and a > h and h == 0)),
        "Odd/Even": lambda: _wl(v == ("Odd" if total % 2 else "Even")),
        "Home Odd/Even": lambda: _wl(v == ("Odd" if h % 2 else "Even")),
        "Away Odd/Even": lambda: _wl(v == ("Odd" if a % 2 else "Even")),
        "Exact Goals Number": lambda: _wl(int(v) == total) if v.isdigit() else None,
        "Results/Both Teams Score": lambda: (
            _wl(v == f"{_res(h, a)}/{'Yes' if h > 0 and a > 0 else 'No'}") if "/" in v else None),
        "Result/Total Goals": lambda: _result_total(v, h, a),
        "Total Goals/Both Teams To Score": lambda: _total_btts(v, h, a),
    }
    halves = {
        "First Half Winner": lambda: _wl(v == _res(hh, ha)),
        "Second Half Winner": lambda: _wl(v == _res(sh, sa)),
        "Goals Over/Under First Half": lambda: _ou(hh + ha, side, line),
        "Goals Over/Under - Second Half": lambda: _ou(sh + sa, side, line),
        "Both Teams Score - First Half": lambda: _yn(v, hh > 0 and ha > 0),
        "Both Teams To Score - Second Half": lambda: _yn(v, sh > 0 and sa > 0),
        "Correct Score - First Half": lambda: _wl(_score(v) == (hh, ha)) if _score(v) else None,
        "HT/FT Double": lambda: _wl(v == f"{_res(hh, ha)}/{_res(h, a)}"),
        "Odd/Even - First Half": lambda: _wl(v == ("Odd" if (hh + ha) % 2 else "Even")),
        "Win Both Halves": lambda: _wl((v == "Home" and hh > ha and sh > sa) or (v == "Away" and ha > hh and sa > sh)),
        "To Win Either Half": lambda: _wl((v == "Home" and (hh > ha or sh > sa)) or (v == "Away" and (ha > hh or sa > sh))),
        "Highest Scoring Half": lambda: _wl(v == ("1st Half" if hh + ha > sh + sa else "2nd Half" if sh + sa > hh + ha else "Draw")),
    }
    if market in full:
        return full[market]()
    if market in halves and have_ht:
        return halves[market]()
    return None


def _result_total(v: str, h: int, a: int) -> str | None:
    """'Home/Over 2.5'"""
    from .markets import parse_value

    if "/" not in v:
        return None
    res, ou = v.split("/", 1)
    side, line = parse_value(ou)
    ou_out = _ou(h + a, side, line)
    if ou_out in (None, "void"):
        return None
    return _wl(res == _res(h, a) and ou_out == "won")


def _total_btts(v: str, h: int, a: int) -> str | None:
    """'o/yes 2.5'"""
    try:
        combo, line = v.rsplit(" ", 1)
        ou, btts = combo.split("/")
        line = float(line)
    except ValueError:
        return None
    ou_out = _ou(h + a, "Over" if ou == "o" else "Under", line)
    if ou_out in (None, "void"):
        return None
    return _wl(ou_out == "won" and (btts == "yes") == (h > 0 and a > 0))


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
        def result_for(m, s, l):
            if m in MARKETS:
                return outcome(m, s, l, fx.home_goals, fx.away_goals)
            return market_outcome(m, s, fx.home_goals, fx.away_goals, fx.ht_home_goals, fx.ht_away_goals)
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
