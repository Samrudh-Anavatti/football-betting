"""Public read API — serves only what's cached in our DB, never calls providers."""
import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Fixture, League, MatchContext, Tip
from ..serialize import fixture_dict, iso, league_dict, tip_dict
from ..services.board import best_1x2, latest_snapshots, match_board
from ..services.settlement import FINISHED
from ..services.stats import tip_record

router = APIRouter(tags=["public"])


@router.get("/leagues")
def leagues(db: Session = Depends(get_db)):
    return [league_dict(lg) for lg in db.scalars(select(League).order_by(League.id.in_([2, 3]), League.country))]


@router.get("/fixtures")
def fixtures(
    when: str = Query("upcoming", pattern="^(upcoming|results)$"),
    league_id: list[int] | None = Query(None),
    country: str | None = None,
    days: int = Query(7, ge=1, le=60),
    limit: int = Query(300, le=1000),
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()
    q = select(Fixture).join(League)
    if when == "upcoming":
        # Include matches in play (kicked off < 2h ago and not finished).
        q = q.where(Fixture.kickoff >= now - timedelta(hours=2), Fixture.kickoff <= now + timedelta(days=days),
                    Fixture.status.not_in(FINISHED)).order_by(Fixture.kickoff)
    else:
        q = q.where(Fixture.status.in_(FINISHED), Fixture.kickoff >= now - timedelta(days=days)).order_by(Fixture.kickoff.desc())
    if league_id:
        q = q.where(Fixture.league_id.in_(league_id))
    if country:
        q = q.where(League.country == country)
    rows = list(db.scalars(q.limit(limit)))
    odds = latest_snapshots(db, [f.id for f in rows]) if when == "upcoming" else {}
    return [fixture_dict(f, best_1x2(odds.get(f.id, []))) for f in rows]


def _standing_rows(fx: Fixture) -> list:
    if not fx.league.standings_json:
        return []
    ids = {fx.home_team_id, fx.away_team_id}
    return [r for r in json.loads(fx.league.standings_json) if r["team_id"] in ids]


@router.get("/matches/{fixture_id}")
def match(fixture_id: int, db: Session = Depends(get_db)):
    """Everything we know about one match: the same bundle Ivo and the AI read."""
    fx = db.get(Fixture, fixture_id)
    if fx is None:
        raise HTTPException(404, "Match not found")
    rows = latest_snapshots(db, [fx.id]).get(fx.id, [])
    board = match_board(db, fx.id)
    return {
        "fixture": fixture_dict(fx, best_1x2(rows)),
        "odds": {**board, "pulled_at": iso(board["pulled_at"])},
        "context": context_dict(db.get(MatchContext, fixture_id)),
        "standings": {"synced_at": iso(fx.league.standings_synced_at), "rows": _standing_rows(fx)},
        "tips": [tip_dict(t, with_fixture=False) for t in
                 db.scalars(select(Tip).where(Tip.fixture_id == fx.id, Tip.published.is_(True)))],
    }


def context_dict(ctx: MatchContext | None) -> dict:
    load = lambda s: json.loads(s) if s else None  # noqa: E731
    if ctx is None:
        ctx = MatchContext()
    return {
        "fetched_at": iso(ctx.fetched_at),
        "h2h": load(ctx.h2h_json),
        "home_form": load(ctx.home_form_json),
        "away_form": load(ctx.away_form_json),
        "injuries": load(ctx.injuries_json),
        "prediction": load(ctx.prediction_json),
        "home_stats": load(ctx.home_stats_json),
        "away_stats": load(ctx.away_stats_json),
        "lineups": load(ctx.lineups_json),
        "lineups_fetched_at": iso(ctx.lineups_fetched_at),
        "errors": load(ctx.errors_json),
    }


@router.get("/tips")
def tips(status: str = Query("open", pattern="^(open|settled|all)$"), limit: int = 50, db: Session = Depends(get_db)):
    q = select(Tip).join(Fixture).where(Tip.published.is_(True), Tip.source == "ivo")
    if status == "open":
        q = q.where(Tip.status == "pending").order_by(Fixture.kickoff)
    elif status == "settled":
        q = q.where(Tip.status != "pending").order_by(Fixture.kickoff.desc())
    else:
        q = q.order_by(Fixture.kickoff.desc())
    return [tip_dict(t) for t in db.scalars(q.limit(limit))]


@router.get("/record")
def record(db: Session = Depends(get_db)):
    return tip_record(db, list(db.scalars(select(Tip).where(Tip.published.is_(True), Tip.source == "ivo"))))
