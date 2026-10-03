"""Turn stored price snapshots into the "odds board" for a match.

For each market/selection we show every bookmaker's latest price, the best
price, and a consensus "fair" price (average implied probability across books,
with the bookmaker margin stripped out). Best vs fair is a quick value signal.
"""
from collections import defaultdict
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import OddsSnapshot

SELECTION_ORDER = {"home": 0, "draw": 1, "away": 2, "over": 0, "under": 1, "yes": 0, "no": 1}


def latest_snapshots(db: Session, fixture_ids: list[int], before: datetime | None = None) -> dict[int, list[OddsSnapshot]]:
    """Rows from each fixture's most recent pull (optionally the last pull before `before`)."""
    if not fixture_ids:
        return {}
    q = select(OddsSnapshot.fixture_id, func.max(OddsSnapshot.pulled_at)).where(OddsSnapshot.fixture_id.in_(fixture_ids))
    if before is not None:
        q = q.where(OddsSnapshot.pulled_at <= before)
    latest = dict(db.execute(q.group_by(OddsSnapshot.fixture_id)).all())
    out: dict[int, list[OddsSnapshot]] = defaultdict(list)
    for fid, pulled in latest.items():
        out[fid] = list(db.scalars(select(OddsSnapshot).where(OddsSnapshot.fixture_id == fid, OddsSnapshot.pulled_at == pulled)))
    return out


def _main_ou_line(rows: list[OddsSnapshot]) -> float | None:
    lines = defaultdict(int)
    for r in rows:
        if r.market == "OU" and r.line is not None:
            lines[r.line] += 1
    if not lines:
        return None
    return max(lines, key=lambda l: (lines[l], l == 2.5))


def build_board(rows: list[OddsSnapshot]) -> dict:
    """{markets: [{market, line, selections: [{selection, best, best_bookmaker, fair, edge, prices}]}], bookmakers, pulled_at}"""
    if not rows:
        return {"markets": [], "bookmakers": [], "pulled_at": None}
    groups: dict[tuple, dict[str, list[OddsSnapshot]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        groups[(r.market, r.line)][r.selection].append(r)

    markets = []
    for (market, line), sels in groups.items():
        # Fair price per book needs that book's full set of outcomes.
        books = defaultdict(dict)
        for sel, rs in sels.items():
            for r in rs:
                books[r.bookmaker_key][sel] = r.price
        n_out = 3 if market == "1X2" else 2
        fair_probs = defaultdict(list)
        for prices in books.values():
            if len(prices) != n_out:
                continue
            total = sum(1 / p for p in prices.values())
            for sel, p in prices.items():
                fair_probs[sel].append((1 / p) / total)
        selections = []
        for sel, rs in sels.items():
            best = max(rs, key=lambda r: r.price)
            probs = fair_probs.get(sel)
            fair = round(len(probs) / sum(probs), 2) if probs else None
            selections.append({
                "selection": sel,
                "best": best.price,
                "best_bookmaker": best.bookmaker,
                "fair": fair,
                "edge": round(best.price / fair - 1, 4) if fair else None,
                "prices": sorted(({"bookmaker": r.bookmaker, "key": r.bookmaker_key, "price": r.price} for r in rs),
                                 key=lambda p: -p["price"]),
            })
        selections.sort(key=lambda s: SELECTION_ORDER.get(s["selection"], 9))
        margins = [sum(1 / p for p in b.values()) - 1 for b in books.values() if len(b) == n_out]
        markets.append({
            "market": market, "line": line, "selections": selections,
            "avg_margin": round(sum(margins) / len(margins), 4) if margins else None,
        })
    main_line = _main_ou_line(rows)
    markets.sort(key=lambda m: (m["market"] != "1X2", m["line"] != main_line, m["line"] or 0))
    return {
        "markets": markets,
        "main_ou_line": main_line,
        "bookmakers": sorted({r.bookmaker for r in rows}),
        "pulled_at": max(r.pulled_at for r in rows),
    }


def best_1x2(rows: list[OddsSnapshot]) -> dict | None:
    """Compact best-price summary for fixture lists."""
    best = {}
    for r in rows:
        if r.market == "1X2" and (r.selection not in best or r.price > best[r.selection]):
            best[r.selection] = r.price
    return best or None
