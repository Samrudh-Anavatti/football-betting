"""Prices for the site: the match board (see markets.py) and the compact
best-price summary on fixture lists, which reads odds_snapshots.
"""
import json
from collections import defaultdict
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import MarketBook, OddsSnapshot
from .markets import book_from_snapshots, build_board


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


def match_board(db: Session, fx_id: int) -> dict:
    """The market board for one match: API-Football's full book if we have one,
    otherwise whatever core-market snapshots exist (e.g. from The Odds API)."""
    book = db.get(MarketBook, fx_id)
    if book is not None:
        return build_board(json.loads(book.bookmakers_json), book.pulled_at, "api_football")
    rows = latest_snapshots(db, [fx_id]).get(fx_id, [])
    if not rows:
        return build_board([], None, "none")
    return build_board(book_from_snapshots(rows), rows[0].pulled_at, "odds_api")


def best_1x2(rows: list[OddsSnapshot]) -> dict | None:
    """Compact best-price summary for fixture lists."""
    best = {}
    for r in rows:
        if r.market == "1X2" and (r.selection not in best or r.price > best[r.selection]):
            best[r.selection] = r.price
    return best or None
