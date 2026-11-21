"""Public read API — serves only what's cached in our DB, never calls providers."""
import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import access
from ..database import get_db
from ..deps import optional_user
from ..models import AiPrediction, Fixture, League, Lineup, MatchContext, Tip, User
from ..serialize import fixture_dict, iso, league_dict, tip_dict
from ..services.board import best_1x2, latest_snapshots, match_board
from ..services.settlement import FINISHED
from ..services.stats import RECORD_DAYS, record_since, tip_record
from ..services.transfermarkt import team_url

router = APIRouter(tags=["public"])


def public_tip(t: Tip, with_fixture: bool = True) -> dict:
    """A pick as the public sees it: no names of who made it."""
    d = tip_dict(t, with_fixture)
    del d["author"]
    return d


FREE_PICKS = 3  # open picks a visitor sees in full


def free_tip_ids(db: Session, now: datetime) -> set[int]:
    """The open picks anyone may see: the most confident few among matches still to kick off, soonest first on a
    tie. The same few for everyone, and it only changes as matches start or picks are added."""
    rows = db.scalars(select(Tip).join(Fixture).where(Tip.published.is_(True), Tip.source == "ivo", Tip.status == "pending",
                                                      Fixture.kickoff > now))
    ranked = sorted(rows, key=lambda t: (-(t.confidence or 0), t.fixture.kickoff, t.id))
    return {t.id for t in ranked[:FREE_PICKS]}


def tip_gate(db: Session, user: User | None):
    """A test for "is this pick hidden from this viewer?". Only picks on matches that haven't kicked off are ever
    hidden: once the match starts the pick is on the record for everyone."""
    if access.can(user, "all_picks"):
        return lambda t: False
    now = datetime.utcnow()
    free = free_tip_ids(db, now)
    return lambda t: t.status == "pending" and t.fixture.kickoff > now and t.id not in free


# Main leagues first (UEFA competitions after the countries), then supplementary by country.
LEAGUE_ORDER = (League.supplementary, League.id.in_([2, 3, 848, 5]), League.country, League.id)


@router.get("/leagues")
def leagues(db: Session = Depends(get_db)):
    return [league_dict(lg) for lg in db.scalars(select(League).order_by(*LEAGUE_ORDER))]


@router.get("/fixtures")
def fixtures(
    when: str = Query("upcoming", pattern="^(upcoming|results)$"),
    league_id: list[int] | None = Query(None),
    country: str | None = None,
    tier: str = Query("all", pattern="^(all|main|more)$"),  # more = supplementary leagues
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
    if tier != "all":
        q = q.where(League.supplementary.is_(tier == "more"))
    rows = list(db.scalars(q.limit(limit)))
    odds = latest_snapshots(db, [f.id for f in rows], market="1X2") if when == "upcoming" else {}
    return [fixture_dict(f, best_1x2(odds.get(f.id, []))) for f in rows]


def _standing_rows(fx: Fixture) -> list:
    if not fx.league.standings_json:
        return []
    ids = {fx.home_team_id, fx.away_team_id}
    return [r for r in json.loads(fx.league.standings_json) if r["team_id"] in ids]


@router.get("/matches/{fixture_id}")
def match(fixture_id: int, db: Session = Depends(get_db), user: User | None = Depends(optional_user)):
    """Everything we know about one match: the same bundle Ivo and the AI read."""
    fx = db.get(Fixture, fixture_id)
    if fx is None:
        raise HTTPException(404, "Match not found")
    rows = latest_snapshots(db, [fx.id]).get(fx.id, [])
    board = match_board(db, fx.id)
    tips = list(db.scalars(select(Tip).where(Tip.fixture_id == fx.id, Tip.published.is_(True))))
    locked = tip_gate(db, user)
    return {
        "fixture": fixture_dict(fx, best_1x2(rows)),
        "odds": {**board, "pulled_at": iso(board["pulled_at"])},
        "context": context_dict(db.get(MatchContext, fixture_id)),
        "standings": {"synced_at": iso(fx.league.standings_synced_at), "rows": _standing_rows(fx)},
        "tips": [public_tip(t, with_fixture=False) for t in tips if not locked(t)],
        "locked_tips": sum(1 for t in tips if locked(t)),  # picks an account would see
        "ai": ai_dict(latest_prediction(db, fx), fx, user),
        "pitch": pitch_dict(db, fx),
    }


@router.get("/matches/{fixture_id}/meta")
def match_meta(fixture_id: int, db: Session = Depends(get_db)):
    """Just enough to title a match page for search engines and link previews (the full match is ~400 KB)."""
    fx = db.get(Fixture, fixture_id)
    if fx is None:
        raise HTTPException(404, "Match not found")
    tips = db.scalars(select(Tip).where(Tip.fixture_id == fx.id, Tip.published.is_(True)))
    locked = tip_gate(db, None)  # search engines and link previews are visitors
    return {
        "fixture": fixture_dict(fx),
        "tips": [{"market": t.market, "selection": t.selection, "line": t.line, "odds": t.odds} for t in tips
                 if not locked(t)],
        "has_ai": latest_prediction(db, fx) is not None,
    }


def pitch_dict(db: Session, fx: Fixture) -> dict:
    """Each team's XI for the pitch card: the confirmed one once it's out, otherwise the
    one it started its previous match with (from the research's last-five list)."""
    ctx = db.get(MatchContext, fx.id)
    own = db.get(Lineup, fx.id)
    confirmed = json.loads(own.data_json) if own else []

    def side(team, form_json):
        xi = next((t for t in confirmed if t["team_id"] == team.id), None)
        source, last = ("confirmed", None) if xi else (None, None)
        rows = json.loads(form_json) if form_json else []
        if xi is None and rows:
            prev = db.get(Lineup, rows[0]["id"])
            xi = next((t for t in json.loads(prev.data_json) if t["team_id"] == team.id), None) if prev else None
            if xi:
                m = rows[0]
                source = "previous"
                last = {"date": m["date"], "league": m["league"], "venue": m["venue"], "gf": m["gf"], "ga": m["ga"],
                        "result": m["result"], "opponent": m["away"] if m["venue"] == "H" else m["home"]}
        return {"team_id": team.id, "transfermarkt": team_url(team.id, team.name), "source": source,
                "previous_match": last, **(xi or {})}

    return {"home": side(fx.home_team, ctx.home_form_json if ctx else None),
            "away": side(fx.away_team, ctx.away_form_json if ctx else None)}


def latest_prediction(db: Session, fx: Fixture) -> AiPrediction | None:
    """The AI's last analysis before kick-off (the one its record is judged on)."""
    return db.scalar(select(AiPrediction).where(AiPrediction.fixture_id == fx.id, AiPrediction.created_at < fx.kickoff)
                     .order_by(AiPrediction.id.desc()).limit(1))


def ai_dict(pred: AiPrediction | None, fx: Fixture, user: User | None) -> dict | None:
    """Public view of an analysis: the read, probabilities and suggested bets. Read-only:
    nobody outside can start one, and the AI's tracked tips stay private. Until kick-off the suggested bets are
    for accounts (`ai_bets`): a visitor gets the read and probabilities, and how many bets are waiting."""
    if pred is None:
        return None
    analysis = json.loads(pred.analysis_json)
    analysis.pop("bundle_legs", None)  # the AI staking test's legs are admin-only
    bets_locked = 0
    if not access.can(user, "ai_bets") and fx.kickoff > datetime.utcnow():
        bets_locked = len(analysis.get("suggested_bets") or [])
        analysis["suggested_bets"] = []
    return {"id": pred.id, "created_at": iso(pred.created_at), "model": pred.model,
            "analysis": analysis, "bets_locked": bets_locked,
            "market_probs": json.loads(pred.market_probs_json) if pred.market_probs_json else None, "tips": []}


# The home page's preview card prefers these competitions, then the next kick-off anywhere.
FEATURED_LEAGUES = [39, 2, 140, 135, 78, 61, 3]


@router.get("/sitemap")
def sitemap(db: Session = Depends(get_db)):
    """Every match from the last 30 days and the next 14, just enough for the frontend's sitemap.xml to build
    each one's address (/match/<teams>-<id>)."""
    now = datetime.utcnow()
    q = select(Fixture).where(Fixture.kickoff >= now - timedelta(days=30), Fixture.kickoff <= now + timedelta(days=14))
    return [{"id": f.id, "home": {"name": f.home_team.name}, "away": {"name": f.away_team.name}}
            for f in db.scalars(q.order_by(Fixture.kickoff))]


@router.get("/featured")
def featured(db: Session = Depends(get_db), user: User | None = Depends(optional_user)):
    """One upcoming match with an AI analysis, for the home page's preview card."""
    now = datetime.utcnow()
    rows = list(db.scalars(
        select(Fixture).join(AiPrediction, AiPrediction.fixture_id == Fixture.id).join(League)
        .where(League.supplementary.is_(False), Fixture.status.in_(("NS", "TBD")), Fixture.kickoff > now + timedelta(minutes=10),
               Fixture.kickoff <= now + timedelta(days=3))
        .group_by(Fixture.id).order_by(Fixture.kickoff)))
    if not rows:
        return None
    fx = min(rows, key=lambda f: (FEATURED_LEAGUES.index(f.league_id) if f.league_id in FEATURED_LEAGUES
                                  else len(FEATURED_LEAGUES), f.kickoff))
    if fx.kickoff > rows[0].kickoff + timedelta(hours=36):
        fx = rows[0]  # don't feature Sunday's big game on a Tuesday when something kicks off sooner
    snaps = latest_snapshots(db, [fx.id]).get(fx.id, [])
    return {"fixture": fixture_dict(fx, best_1x2(snaps)), "ai": ai_dict(latest_prediction(db, fx), fx, user)}


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
def tips(status: str = Query("open", pattern="^(open|settled|all)$"), limit: int = Query(50, ge=1, le=1000),
         db: Session = Depends(get_db), user: User | None = Depends(optional_user)):
    """Our picks. A visitor gets the settled picks but only the free few of the open ones; `/tips/locked` says
    which matches the rest are on. `settled` is the record's list: matches from the last `RECORD_DAYS` days."""
    q = select(Tip).join(Fixture).where(Tip.published.is_(True), Tip.source == "ivo")
    if status == "open":
        q = q.where(Tip.status == "pending").order_by(Fixture.kickoff)
    elif status == "settled":
        q = q.where(Tip.status != "pending", Fixture.kickoff >= record_since()).order_by(Fixture.kickoff.desc())
    else:
        q = q.order_by(Fixture.kickoff.desc())
    locked = tip_gate(db, user)
    return [public_tip(t) for t in db.scalars(q.limit(limit)) if not locked(t)]


@router.get("/tips/locked")
def locked_tips(db: Session = Depends(get_db), user: User | None = Depends(optional_user)):
    """The open picks this viewer can't see yet, as the match and kick-off only (never the selection or price),
    for the "join to see these" cards. Empty for anyone who sees them all."""
    locked = tip_gate(db, user)
    q = (select(Tip).join(Fixture).where(Tip.published.is_(True), Tip.source == "ivo", Tip.status == "pending")
         .order_by(Fixture.kickoff))
    return [{"id": t.id, "fixture": fixture_dict(t.fixture)} for t in db.scalars(q) if locked(t)]


@router.get("/record")
def record(db: Session = Depends(get_db)):
    """Our picks' record over the last `RECORD_DAYS` days (by kick-off), and `days` so pages can say so."""
    q = select(Tip).join(Fixture).where(Tip.published.is_(True), Tip.source == "ivo", Fixture.kickoff >= record_since())
    return {**tip_record(db, list(db.scalars(q))), "days": RECORD_DAYS}
