"""Settle tips and bets from final scores (90 minutes, like the bookies do).

Two vocabularies: our short codes (1X2/OU/BTTS) and API-Football market names
for everything else on the board. Anything that needs more than the full-time
and half-time scores (scorers, corners, cards, Asian quarter lines...) returns
None and is settled by hand in Admin, Picks.
"""
import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Bet, Fixture, Tip
from .stats import record_closing_prices

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


def _exact(v: str, n: int) -> str | None:
    """'2' or 'more 4' (4 or more)."""
    if v.isdigit():
        return _wl(n == int(v))
    if v.startswith("more ") and v[5:].isdigit():
        return _wl(n >= int(v[5:]))
    return None


def _european(v: str, h: int, a: int) -> str | None:
    """Three-way handicap. The line is the home team's: 'Away -1' means away +1."""
    from .markets import parse_value

    side, line = parse_value(v)
    if side not in ("Home", "Draw", "Away") or line is None or line != int(line):
        return None
    return _wl(side == _res(h + int(line), a))


def _asian(v: str, h: int, a: int) -> str | None:
    """The line is the home team's. Quarter lines (half win/loss) are settled by hand."""
    from .markets import parse_value

    side, line = parse_value(v)
    if side not in ("Home", "Away") or line is None or line * 4 % 2 == 1:
        return None
    diff = h + line - a
    if diff == 0:
        return "void"
    return _wl((side == "Home") == (diff > 0))


def _margin(v: str, h: int, a: int) -> str | None:
    """'1 by 2' (home by 2), '2 by 4+' (away by 4 or more), 'Score Draw', 'Draw' (0-0)."""
    if v == "Draw":
        return _wl(h == a == 0)
    if v == "Score Draw":
        return _wl(h == a > 0)
    m = re.fullmatch(r"([12]) by (\d+)(\+?)", v)
    if not m:
        return None
    won_by = h - a if m[1] == "1" else a - h
    n = int(m[2])
    return _wl(won_by >= n if m[3] else won_by == n)


def _goal_band(v: str, total: int) -> str | None:
    """'Under 2 goals', '2 or 3 goals', 'Over 3 goals'."""
    if m := re.fullmatch(r"Under (\d+) goals", v):
        return _wl(total < int(m[1]))
    if m := re.fullmatch(r"Over (\d+) goals", v):
        return _wl(total > int(m[1]))
    if m := re.fullmatch(r"(\d+) or (\d+) goals", v):
        return _wl(total in (int(m[1]), int(m[2])))
    return None


def _half(first: int, second: int) -> str:
    return "1st Half" if first > second else "2nd Half" if second > first else "Draw"


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
        "Exact Goals Number": lambda: _exact(v, total),
        "Home Team Exact Goals Number": lambda: _exact(v, h),
        "Away Team Exact Goals Number": lambda: _exact(v, a),
        "Home Team Score a Goal": lambda: _yn(v, h > 0),
        "Away Team Score a Goal": lambda: _yn(v, a > 0),
        "Handicap Result": lambda: _european(v, h, a),
        "Asian Handicap": lambda: _asian(v, h, a),
        "Goal Line": lambda: _ou(total, side, line),
        "Winning Margin": lambda: _margin(v, h, a),
        "Number Of Goals In Match": lambda: _goal_band(v, total),
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
        "Highest Scoring Half": lambda: _wl(v == _half(hh + ha, sh + sa)),
        "Home Highest Scoring Half": lambda: _wl(v == _half(hh, sh)),
        "Away Highest Scoring Half": lambda: _wl(v == _half(ha, sa)),
        "Handicap Result - First Half": lambda: _european(v, hh, ha),
        "Asian Handicap First Half": lambda: _asian(v, hh, ha),
        "Double Chance - First Half": lambda: _wl(_res(hh, ha) in v.split("/")) if "/" in v else None,
        "Double Chance - Second Half": lambda: _wl(_res(sh, sa) in v.split("/")) if "/" in v else None,
        "Exact Goals Number - First Half": lambda: _exact(v, hh + ha),
        "Second Half Exact Goals Number": lambda: _exact(v, sh + sa),
        "Correct Score - Second Half": lambda: _wl(_score(v) == (sh, sa)) if _score(v) else None,
        "Odd/Even - Second Half": lambda: _wl(v == ("Odd" if (sh + sa) % 2 else "Even")),
        "Goal Line (1st Half)": lambda: _ou(hh + ha, side, line),
        "Home Team Total Goals(1st Half)": lambda: _ou(hh, side, line),
        "Away Team Total Goals(1st Half)": lambda: _ou(ha, side, line),
        "Home Team Score a Goal (1st Half)": lambda: _yn(v, hh > 0),
        "Away Team Score a Goal (1st Half)": lambda: _yn(v, ha > 0),
        "Home Team Score a Goal (2nd Half)": lambda: _yn(v, sh > 0),
        "Away Team Score a Goal (2nd Half)": lambda: _yn(v, sa > 0),
        "Home team will score in both halves": lambda: _yn(v, hh > 0 and sh > 0),
        "Away team will score in both halves": lambda: _yn(v, ha > 0 and sa > 0),
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
    tips = list(db.scalars(select(Tip).where(Tip.fixture_id == fx.id, Tip.status == "pending")))
    record_closing_prices(db, tips)
    for tip in tips:
        if (res := result_for(tip.market, tip.selection, tip.line)) is not None:
            apply_result(tip, res, tip.stake_units)
            n += 1
    for bet in db.scalars(select(Bet).where(Bet.fixture_id == fx.id, Bet.status == "pending")):
        if (res := result_for(bet.market, bet.selection, bet.line)) is not None:
            apply_result(bet, res, bet.stake)
            n += 1
    return n


def settle_pending(db: Session) -> int:
    """Re-run settlement over every fixture with pending tips/bets (no API calls).

    Runs at startup, so new settlement rules apply to matches that already finished.
    """
    ids = set(db.scalars(select(Tip.fixture_id).where(Tip.status == "pending"))) | set(
        db.scalars(select(Bet.fixture_id).where(Bet.status == "pending")))
    n = sum(settle_fixture(db, db.get(Fixture, i)) for i in ids)
    # Backfill closing prices for any match that has started (tips from before the column existed).
    record_closing_prices(db, db.scalars(select(Tip).where(Tip.closing_checked_at.is_(None))))
    db.commit()
    return n
