"""Signed-in AI endpoints: analyse a match with Claude, chat about it, and see
how the AI's calls are doing against the market and Ivo."""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..ai import client as ai_client
from ..ai import service
from ..ai.bundle import build_bundle, serialise
from ..database import get_db
from ..deps import current_user
from ..models import AiPrediction, AiThread, Fixture, SyncRun, Tip, User
from ..serialize import fixture_dict, iso, run_dict, tip_dict
from ..services import sync
from ..services.settlement import FINISHED
from ..services.stats import tip_record

router = APIRouter(prefix="/admin", tags=["ai"], dependencies=[Depends(current_user)])


def _budget(db: Session) -> dict:
    return {"spent_usd": service.month_spend(db), "limit_usd": config.AI_MONTHLY_BUDGET_USD}


def _guard(db: Session):
    if not ai_client.configured():
        raise HTTPException(400, "Claude isn't connected: set FOUNDRY_RESOURCE and FOUNDRY_API_KEY in the App Service settings")
    if sync.running_run(db, "claude"):
        raise HTTPException(409, "Claude is already working on something; wait for it to finish")
    b = _budget(db)
    if b["spent_usd"] >= b["limit_usd"]:
        raise HTTPException(402, f"This month's AI budget (${b['limit_usd']:.0f}) is used up. Raise AI_MONTHLY_BUDGET_USD to continue.")


def _fixture(db: Session, fixture_id: int) -> Fixture:
    fx = db.get(Fixture, fixture_id)
    if fx is None:
        raise HTTPException(404, "Match not found")
    return fx


def _jsonable(d):
    """Datetimes inside thread views -> ISO strings."""
    if isinstance(d, dict):
        return {k: _jsonable(v) for k, v in d.items()}
    if isinstance(d, list):
        return [_jsonable(v) for v in d]
    return iso(d) if hasattr(d, "isoformat") else d


@router.get("/matches/{fixture_id}/ai")
def match_ai(fixture_id: int, db: Session = Depends(get_db)):
    fx = _fixture(db, fixture_id)
    threads = list(db.scalars(select(AiThread).where(AiThread.fixture_id == fx.id).order_by(AiThread.id.desc())))
    running = sync.running_run(db, "claude")
    bundle_text, _ = serialise(build_bundle(db, fx))
    tips = list(db.scalars(select(Tip).where(Tip.fixture_id == fx.id, Tip.source == "ai")))
    return {
        "configured": ai_client.configured(),
        "provider": ai_client.provider_name(),
        "model": config.AI_MODEL,
        "effort": config.AI_EFFORT,
        "budget": _budget(db),
        "estimate_usd": service.estimate_cost(bundle_text),
        "running": run_dict(running) if running else None,
        "threads": [_jsonable(service.thread_view(db, t)) for t in threads],
        "tips": [tip_dict(t, with_fixture=False) for t in tips],
    }


@router.post("/matches/{fixture_id}/ai")
def analyse(fixture_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Start a new thread with a freshly built bundle and ask for an analysis."""
    fx = _fixture(db, fixture_id)
    if fx.status != "NS":
        raise HTTPException(409, "Only matches that haven't started can be analysed")
    _guard(db)
    thread = service.new_thread(db, fx, user)
    run = sync.start_run(db, "claude", "analysis", f"{fx.home_team.name} v {fx.away_team.name}", 1,
                         user.display_name, service.job_turn, thread.id, user.id, True)
    return run_dict(run)


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.post("/ai/threads/{thread_id}/messages")
def chat(thread_id: int, body: ChatIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    thread = db.get(AiThread, thread_id)
    if thread is None:
        raise HTTPException(404, "Conversation not found")
    fx = _fixture(db, thread.fixture_id)
    _guard(db)
    service.add_user_message(db, thread, user, body.text.strip())
    run = sync.start_run(db, "claude", "chat", f"{fx.home_team.name} v {fx.away_team.name}", 1,
                         user.display_name, service.job_turn, thread.id, user.id, False)
    return run_dict(run)


# ── How the AI is doing ──────────────────────────────────────────────────────


def _brier(probs: dict[str, float], actual: str) -> float | None:
    if not probs or any(probs.get(k) is None for k in ("home", "draw", "away")):
        return None
    total = sum(probs[k] for k in ("home", "draw", "away")) or 1
    return sum((probs[k] / total - (1.0 if k == actual else 0.0)) ** 2 for k in ("home", "draw", "away"))


def _binary_brier(p: float | None, happened: bool) -> float | None:
    return None if p is None else (p - (1.0 if happened else 0.0)) ** 2


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 4) if xs else None


@router.get("/ai/summary")
def summary(db: Session = Depends(get_db)):
    """Spend, the AI's betting record next to Ivo's, and probability scores vs the market."""
    # Latest prediction before kick-off per finished fixture.
    rows = db.execute(
        select(AiPrediction, Fixture).join(Fixture, AiPrediction.fixture_id == Fixture.id)
        .where(Fixture.status.in_(FINISHED), AiPrediction.created_at < Fixture.kickoff)
        .order_by(AiPrediction.id)
    ).all()
    latest = {}
    for pred, fx in rows:
        latest[fx.id] = (pred, fx)
    scored = []
    for pred, fx in latest.values():
        if fx.home_goals is None:
            continue
        h, a = fx.home_goals, fx.away_goals
        actual = "home" if h > a else "away" if a > h else "draw"
        ai = json.loads(pred.analysis_json)["probabilities"]
        mk = json.loads(pred.market_probs_json or "{}")
        scored.append({
            "fixture": fixture_dict(fx),
            "prediction_id": pred.id,
            "ai_result": _brier({"home": ai.get("home_win"), "draw": ai.get("draw"), "away": ai.get("away_win")}, actual),
            "market_result": _brier(mk.get("result") or {}, actual),
            "ai_over": _binary_brier(ai.get("over_2_5_goals"), h + a > 2.5),
            "market_over": _binary_brier(mk.get("over_2_5"), h + a > 2.5),
            "ai_btts": _binary_brier(ai.get("both_teams_score"), h > 0 and a > 0),
            "market_btts": _binary_brier(mk.get("btts_yes"), h > 0 and a > 0),
        })
    threads = list(db.scalars(select(AiThread).order_by(AiThread.id.desc()).limit(20)))
    recent = []
    for t in threads:
        fx = db.get(Fixture, t.fixture_id)
        view = service.thread_view(db, t)
        recent.append({"thread_id": t.id, "fixture": fixture_dict(fx), "created_at": iso(t.created_at),
                       "created_by": t.created_by, "cost_usd": view["cost_usd"], "model": t.model,
                       "predictions": len(view["predictions"])})
    ai_tips = list(db.scalars(select(Tip).where(Tip.source == "ai")))
    ivo_tips = list(db.scalars(select(Tip).where(Tip.source == "ivo", Tip.published.is_(True))))
    return {
        "configured": ai_client.configured(),
        "provider": ai_client.provider_name(),
        "model": config.AI_MODEL,
        "budget": _budget(db),
        "records": {"ai": tip_record(db, ai_tips), "ivo": tip_record(db, ivo_tips)},
        "scores": {
            "matches": len(scored),
            "result": {"ai": _avg(s["ai_result"] for s in scored), "market": _avg(s["market_result"] for s in scored)},
            "over_2_5": {"ai": _avg(s["ai_over"] for s in scored), "market": _avg(s["market_over"] for s in scored)},
            "btts": {"ai": _avg(s["ai_btts"] for s in scored), "market": _avg(s["market_btts"] for s in scored)},
            "rows": scored[-30:][::-1],
        },
        "recent": recent,
        "runs": [run_dict(r) for r in db.scalars(select(SyncRun).where(SyncRun.provider == "claude")
                                                  .order_by(SyncRun.id.desc()).limit(10))],
    }
