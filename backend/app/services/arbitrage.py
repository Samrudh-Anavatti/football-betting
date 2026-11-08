"""Arbitrage scanner (AI Lab): no API calls, just the market books we already pull.

For each complete market (every outcome, mutually exclusive), take the best price for each outcome across our
bookmakers. If 1/price summed over the outcomes is under 1, backing each outcome with that share of the total
stake returns the same amount whatever happens: profit = 1 / sum − 1.

Only sets a single bookmaker prices in full at a normal margin count as complete (the same test as fair prices, so
double chance, scorer lists and the like are out), and only half lines (2.5, -1.5): on whole or quarter lines a
push refunds stakes, which can't lose but doesn't lock in a profit.
"""
import json
import statistics
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ArbSighting, Fixture, MarketBook, Setting
from ..serialize import fixture_dict, iso
from .markets import build_markets

SUSPECT_ABOVE = 0.10  # a "profit" this big is almost always a wrong or stale price
SCAN_KEY = "arb_scanned_at"
TS_FMT = "%Y-%m-%dT%H:%M:%S.%f"


def find_arbs(bookmakers: list[dict]) -> list[dict]:
    out = []
    for m in build_markets(bookmakers):
        for g in m["groups"]:
            sels = g["selections"]
            if len(sels) < 2 or g["margin"] is None:
                continue  # no bookmaker prices the whole set, so it may not be complete
            if g["line"] is not None and (g["line"] * 2) % 2 != 1:
                continue  # whole or quarter line
            total = sum(1 / s["best"] for s in sels)
            if total >= 1:
                continue
            books = {s["best_bookmaker"] for s in sels}
            profit = round(1 / total - 1, 4)
            out.append({
                "key": f"{m['id']}|{g['line']}", "market_id": m["id"], "market": m["name"], "line": g["line"],
                "profit": profit, "suspect": profit > SUSPECT_ABOVE or len(books) == 1,
                "legs": [{"value": s["value"], "bookmaker": s["best_bookmaker"], "price": s["best"],
                          "share": round((1 / s["best"]) / total, 4)} for s in sels],
            })
    return out


def scan(db: Session, now: datetime | None = None) -> int:
    """Check every upcoming match's book pulled since the last scan: open, update or close sightings. Commits.
    Returns how many books were checked."""
    now = now or datetime.utcnow()
    row = db.get(Setting, SCAN_KEY)
    since = datetime.strptime(row.value, TS_FMT) if row else None
    q = select(MarketBook).join(Fixture).where(Fixture.kickoff > now)
    if since:
        q = q.where(MarketBook.pulled_at > since)
    n = 0
    for book in db.scalars(q):
        found = {a["key"]: a for a in find_arbs(json.loads(book.bookmakers_json))}
        open_rows = {s.key: s for s in db.scalars(select(ArbSighting).where(
            ArbSighting.fixture_id == book.fixture_id, ArbSighting.gone_at.is_(None)))}
        for key, a in found.items():
            s = open_rows.get(key)
            if s is None:
                s = ArbSighting(fixture_id=book.fixture_id, key=key, market_id=a["market_id"], market=a["market"],
                                line=a["line"], best_profit=a["profit"], first_seen=book.pulled_at)
                db.add(s)
            s.legs_json, s.profit, s.suspect = json.dumps(a["legs"]), a["profit"], a["suspect"]
            s.best_profit = max(s.best_profit, a["profit"])
            s.last_seen, s.prices_at = book.pulled_at, book.provider_updated_at
        for key, s in open_rows.items():
            if key not in found:
                s.gone_at = book.pulled_at
        n += 1
    # Prices stop at kick-off, so anything still open then ends there.
    for s in db.scalars(select(ArbSighting).join(Fixture).where(ArbSighting.gone_at.is_(None), Fixture.kickoff <= now)):
        s.gone_at = s.fixture.kickoff
    db.merge(Setting(key=SCAN_KEY, value=now.strftime(TS_FMT)))
    db.commit()
    return n


def sighting_dict(s: ArbSighting) -> dict:
    return {
        "id": s.id, "fixture": fixture_dict(s.fixture), "market_id": s.market_id, "market": s.market, "line": s.line,
        "legs": json.loads(s.legs_json), "profit": s.profit, "best_profit": s.best_profit, "suspect": s.suspect,
        "first_seen": iso(s.first_seen), "last_seen": iso(s.last_seen), "prices_at": iso(s.prices_at),
        "gone_at": iso(s.gone_at),
    }


def overview(db: Session, days: int = 7) -> dict:
    now = datetime.utcnow()
    live = list(db.scalars(select(ArbSighting).where(ArbSighting.gone_at.is_(None)).order_by(ArbSighting.profit.desc())))
    recent = list(db.scalars(select(ArbSighting).where(ArbSighting.gone_at >= now - timedelta(days=days))
                             .order_by(ArbSighting.gone_at.desc()).limit(100)))
    genuine = [s for s in recent if not s.suspect]
    row = db.get(Setting, SCAN_KEY)
    return {
        "scanned_at": iso(datetime.strptime(row.value, TS_FMT)) if row else None,
        "live": [sighting_dict(s) for s in live],
        "recent": [sighting_dict(s) for s in recent],
        "stats": {
            "days": days,
            "closed": len(recent),
            "genuine": len(genuine),
            # how long genuine ones stayed visible, from first to last pull that showed them
            "median_minutes": round(statistics.median((s.last_seen - s.first_seen).total_seconds() / 60 for s in genuine))
            if genuine else None,
            "average_profit": round(sum(s.best_profit for s in genuine) / len(genuine), 4) if genuine else None,
        },
    }
