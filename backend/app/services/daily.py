"""The bundle of the day: one accumulator a day at about the plan's target odds, chosen by a model that reads every
candidate leg together, on its own staking run.

Luna analyses each match on its own and leaves legs (`ai_leg`, `ai` tips). Once a day, from PUBLISH_HOUR, Claude is
given all of the day's legs with Luna's reasoning and each bookmaker's prices and picks the bundle, or says there
isn't one today. Luna does the same job when Claude can't (no key, its month's budget spent, an error). The answer is
checked here before anything is stored: real legs, one bookmaker, odds near the target.

The stake is the usual stake plus enough to win back what the run has lost: base + losses ÷ (odds − 1). So the
first bet of a run is exactly the usual stake whatever the bundle's odds, and a win always returns the run's losses
plus what a usual-stake win would have made. After MAX_MISSES misses in a row the run is written off and the next
one starts at the usual stake, so the stake visitors are shown never climbs far.
"""
import json
import math
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config
from ..ai import reviewer
from ..ai.service import month_spend
from ..models import AiCall, AiPrediction, Bundle, BundleLeg, Fixture, Tip
from ..serialize import iso, leg_tip_dict
from .staking import get_plan, plan_bundles
from .stats import current_prices

SOURCE = "daily"
MAX_MISSES = 6
PUBLISH_HOUR, LAST_HOUR = 8, 18  # UTC: the bundle is made from 08:00; nothing new is started after 18:00
DAY_ENDS = timedelta(days=1, hours=5)  # after the day's midnight: late kick-offs (MLS) still belong to the day
LEAD = timedelta(minutes=45)  # a leg must be this far from kick-off, so the bundle can really be placed
MIN_LEGS, MAX_LEGS, PER_MATCH = 3, 8, 2
BAND = (0.85, 1.25)  # of the target odds
MAX_CALLS_A_DAY = 4
PROMPT = (Path(__file__).parent.parent / "ai" / "prompts" / "daily_v1.md").read_text(encoding="utf-8")

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["no_bundle", "reason_if_none", "bookmaker", "legs", "summary"],
    "properties": {
        "no_bundle": {"type": "boolean"},
        "reason_if_none": {"type": "string"},
        "bookmaker": {"type": "string"},
        "legs": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["id", "reason"],
            "properties": {"id": {"type": "integer"}, "reason": {"type": "string"}}}},
        "summary": {"type": "string"},
    },
}


def day_of(now: datetime) -> str:
    return now.strftime("%Y-%m-%d")


def run_state(rows: list[Bundle]) -> dict:
    """The run the next bundle belongs to. A win ends a run; so do MAX_MISSES misses in a row (written off)."""
    run, step, losses = 1, 1, 0.0
    for b in rows:
        if b.status == "won":
            run, step, losses = run + 1, 1, 0.0
        elif b.status == "lost":
            step, losses = step + 1, losses + b.stake
            if step > MAX_MISSES:
                run, step, losses = run + 1, 1, 0.0
    return {"number": run, "step": step, "losses": round(losses, 2)}


def stake_for(plan, losses: float, odds: float) -> float:
    return round(plan.base_stake + losses / (odds - 1), 2)


# ── Spend ────────────────────────────────────────────────────────────────────


def _month_start() -> datetime:
    return datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def calls_spend(db: Session, provider: str) -> float:
    return db.scalar(select(func.coalesce(func.sum(AiCall.cost_usd), 0.0))
                     .where(AiCall.provider == provider, AiCall.created_at >= _month_start())) or 0.0


def spend(db: Session) -> dict:
    """This month's spend and limit per provider. Luna's includes her match analyses; the two budgets are separate."""
    luna = month_spend(db)
    claude = calls_spend(db, "claude")
    return {
        "claude": {"configured": reviewer.configured("claude"), "model": config.CLAUDE_MODEL,
                   "spent_usd": round(claude, 4), "limit_usd": config.CLAUDE_MONTHLY_BUDGET_USD,
                   "left_usd": round(max(config.CLAUDE_MONTHLY_BUDGET_USD - claude, 0), 2)},
        "luna": {"configured": reviewer.configured("foundry"), "model": config.AI_MODEL,
                 "spent_usd": round(luna, 4), "limit_usd": config.AI_MONTHLY_BUDGET_USD,
                 "left_usd": round(max(config.AI_MONTHLY_BUDGET_USD - luna, 0), 2)},
    }


def providers(db: Session) -> list[str]:
    """Who can be asked now, in order: Claude, then Luna, each while configured and inside its month's budget."""
    s = spend(db)
    return [p for p, k in (("claude", "claude"), ("foundry", "luna"))
            if s[k]["configured"] and s[k]["spent_usd"] < s[k]["limit_usd"]]


# ── Candidates and the model's answer ────────────────────────────────────────


def candidates(db: Session, now: datetime) -> list[tuple[Tip, dict[str, float]]]:
    """Today's open legs that aren't in a bundle yet, with each bookmaker's price."""
    day_end = now.replace(hour=0, minute=0, second=0, microsecond=0) + DAY_ENDS
    q = (select(Tip).join(Fixture)
         .where(Tip.source.in_(["ai_leg", "ai"]), Tip.status == "pending", Tip.ai_probability.is_not(None),
                Fixture.status == "NS", Fixture.kickoff > now + LEAD, Fixture.kickoff <= day_end,
                Tip.id.not_in(select(BundleLeg.tip_id)))
         .order_by(Fixture.kickoff, Tip.id))
    return [(t, p) for t in db.scalars(q) if (p := current_prices(db, t))]


def enough(cands: list[tuple[Tip, dict[str, float]]]) -> bool:
    return len(cands) >= MIN_LEGS and len({t.fixture_id for t, _ in cands}) >= 2


def brief(db: Session, cands: list[tuple[Tip, dict[str, float]]], plan, run: dict, day: str) -> str:
    """What the model reads: the day's matches, each with Luna's read and its candidate legs."""
    matches: dict[int, dict] = {}
    for t, prices in cands:
        fx = t.fixture
        m = matches.get(fx.id)
        if m is None:
            pred = db.get(AiPrediction, t.ai_prediction_id) if t.ai_prediction_id else None
            a = json.loads(pred.analysis_json) if pred else {}
            m = matches[fx.id] = {
                "competition": fx.league.name, "home": fx.home_team.name, "away": fx.away_team.name,
                "kickoff_utc": iso(fx.kickoff), "analysis_summary": a.get("summary"),
                "key_factors": a.get("key_factors"), "data_gaps": a.get("data_gaps"), "candidates": [],
            }
        m["candidates"].append({
            "id": t.id, "kind": "sure" if t.source == "ai_leg" else "longer", "market": t.market,
            "selection": t.selection, **({"line": t.line} if t.line is not None else {}),
            "analyst_probability": t.ai_probability, "analyst_reasoning": t.reasoning, "prices": prices,
        })
    return json.dumps({
        "day": day, "target_odds": plan.target_odds,
        "accepted_odds": [round(plan.target_odds * BAND[0], 2), round(plan.target_odds * BAND[1], 2)],
        "staking_run": {"misses_so_far": run["step"] - 1, "written_off_after": MAX_MISSES},
        "matches": list(matches.values()),
    }, ensure_ascii=False)


def check(data: dict, cands: list[tuple[Tip, dict[str, float]]], target: float) -> tuple[str, list[tuple[Tip, float, str]]]:
    """The model's bundle as (bookmaker, [(tip, price, reason)]), or ValueError saying what's wrong with it."""
    by_id = {t.id: (t, prices) for t, prices in cands}
    bookmaker = data["bookmaker"]
    ids = [leg["id"] for leg in data["legs"]]
    if len(set(ids)) != len(ids):
        raise ValueError("a leg is listed twice")
    if not MIN_LEGS <= len(ids) <= MAX_LEGS:
        raise ValueError(f"{len(ids)} legs; it must be {MIN_LEGS} to {MAX_LEGS}")
    chosen = []
    for leg in data["legs"]:
        if leg["id"] not in by_id:
            raise ValueError(f"leg {leg['id']} isn't one of the candidates")
        tip, prices = by_id[leg["id"]]
        if bookmaker not in prices:
            raise ValueError(f"leg {tip.id} has no price at {bookmaker} (it has {', '.join(sorted(prices))})")
        chosen.append((tip, prices[bookmaker], leg["reason"].strip()))
    worst = Counter(t.fixture_id for t, _, _ in chosen).most_common(1)[0][1]
    if worst > PER_MATCH:
        raise ValueError(f"{worst} legs from one match; at most {PER_MATCH}")
    odds = math.prod(p for _, p, _ in chosen)
    lo, hi = target * BAND[0], target * BAND[1]
    if not lo <= odds <= hi:
        raise ValueError(f"the legs multiply to {odds:.2f} at {bookmaker}; it must be between {lo:.2f} and {hi:.2f}")
    return bookmaker, chosen


# ── Building ─────────────────────────────────────────────────────────────────


def _log(db: Session, reply: reviewer.Reply | None, provider: str, day: str, outcome: str, note: str | None) -> None:
    db.add(AiCall(provider=provider, model=reply.model if reply else "", purpose="daily_bundle", day=day,
                  outcome=outcome, note=note, input_tokens=reply.input_tokens if reply else 0,
                  output_tokens=reply.output_tokens if reply else 0, cost_usd=reply.cost_usd if reply else 0.0))
    db.commit()


def due(db: Session, now: datetime) -> bool:
    """Whether to try for today's bundle now: in hours, none made or declined today, the last one settled, calls
    left for the day, someone to ask and enough legs. No model call."""
    if not PUBLISH_HOUR <= now.hour < LAST_HOUR:
        return False
    day = day_of(now)
    rows = plan_bundles(db, get_plan(db, SOURCE))
    if any(b.status == "pending" or b.day == day for b in rows):
        return False
    calls = list(db.scalars(select(AiCall).where(AiCall.purpose == "daily_bundle", AiCall.day == day)))
    if any(c.outcome == "no_bundle" for c in calls) or len(calls) >= MAX_CALLS_A_DAY:
        return False
    return bool(providers(db)) and enough(candidates(db, now))


def build(db: Session, now: datetime | None = None) -> dict:
    """Ask for today's bundle and store it. Each provider gets two goes (the second told what was wrong with the
    first). Returns {"status": bundle | no_bundle | failed | thin, ...}. Commits."""
    now = now or datetime.utcnow()
    day = day_of(now)
    plan = get_plan(db, SOURCE)
    rows = plan_bundles(db, plan)
    run = run_state(rows)
    cands = candidates(db, now)
    if not enough(cands):
        return {"status": "thin", "message": f"Only {len(cands)} open legs today"}
    text = brief(db, cands, plan, run, day)
    errors = []
    for provider in providers(db):
        user = text
        for _ in range(2):
            try:
                reply = reviewer.ask(provider, PROMPT, user, SCHEMA)
            except reviewer.ReviewError as e:
                _log(db, getattr(e, "reply", None), provider, day, "error", str(e))
                errors.append(f"{provider}: {e}")
                break
            if reply.data["no_bundle"]:
                _log(db, reply, provider, day, "no_bundle", reply.data["reason_if_none"])
                return {"status": "no_bundle", "message": reply.data["reason_if_none"], "cost_usd": reply.cost_usd}
            try:
                bookmaker, chosen = check(reply.data, cands, plan.target_odds)
            except ValueError as e:
                _log(db, reply, provider, day, "invalid", str(e))
                errors.append(f"{provider}: {e}")
                user = f"{text}\n\nYour previous answer couldn't be used: {e}. Please answer again."
                continue
            odds = round(math.prod(p for _, p, _ in chosen), 2)
            bundle = Bundle(plan_id=plan.id, run=run["number"], step=run["step"], odds=odds, bookmaker=bookmaker,
                            stake=stake_for(plan, run["losses"], odds), day=day, model=reply.model,
                            summary=reply.data["summary"].strip(),
                            legs=[BundleLeg(tip_id=t.id, odds=p, reason=r) for t, p, r in chosen])
            db.add(bundle)
            _log(db, reply, provider, day, "bundle", None)
            return {"status": "bundle", "bundle_id": bundle.id, "model": reply.model, "cost_usd": reply.cost_usd}
    return {"status": "failed", "message": "; ".join(errors) or "No AI provider is available"}


def job(db: Session, run) -> None:
    """SyncRun job for the schedule and the admin button."""
    out = build(db)
    run.status = {"bundle": "ok", "no_bundle": "ok", "thin": "partial"}.get(out["status"], "error")
    run.items = 1 if out["status"] == "bundle" else 0
    run.message = out.get("message")
    run.details_json = json.dumps(out)
    run.progress = 1
    run.finished_at = datetime.utcnow()
    db.commit()


# ── Views ────────────────────────────────────────────────────────────────────


def bundle_dict(b: Bundle, base_stake: float) -> dict:
    return {
        "id": b.id, "day": b.day, "run": b.run, "step": b.step, "odds": b.odds, "bookmaker": b.bookmaker,
        "stake": b.stake, "multiplier": round(b.stake / base_stake, 2), "returns": round(b.stake * b.odds, 2),
        "status": b.status, "profit": b.profit, "summary": b.summary, "by_claude": (b.model or "").startswith("claude"),
        "created_at": iso(b.created_at), "settled_at": iso(b.settled_at),
        "legs": [{"tip_id": leg.tip_id, "odds": leg.odds, "reason": leg.reason, "tip": leg_tip_dict(leg.tip)}
                 for leg in b.legs],
    }


def state(db: Session, now: datetime | None = None) -> dict:
    """What the site shows: the latest bundle (today's when it's out), where the run stands, this run's earlier
    days, and one line on the run before."""
    now = now or datetime.utcnow()
    day = day_of(now)
    plan = get_plan(db, SOURCE)
    rows = plan_bundles(db, plan)
    run = run_state(rows)
    latest = rows[-1] if rows else None
    live_run = latest.run if latest and latest.status == "pending" else run["number"]
    this_run = [b for b in rows if b.run == live_run and b.status != "pending"]
    before = [b for b in rows if b.run == live_run - 1]
    declined = db.scalar(select(AiCall).where(AiCall.purpose == "daily_bundle", AiCall.day == day,
                                              AiCall.outcome == "no_bundle").order_by(AiCall.id.desc()).limit(1))
    next_stake = stake_for(plan, run["losses"], plan.target_odds)
    return {
        "today": day,
        "publish_hour_utc": PUBLISH_HOUR,
        "plan": {"base_stake": plan.base_stake, "target_odds": plan.target_odds, "max_misses": MAX_MISSES},
        "bundle": bundle_dict(latest, plan.base_stake) if latest else None,
        "no_bundle_today": declined.note if declined else None,
        "run": {"number": run["number"], "misses": run["step"] - 1, "next_stake": next_stake,
                "next_multiplier": round(next_stake / plan.base_stake, 2)},
        "this_run": [bundle_dict(b, plan.base_stake) for b in reversed(this_run)],
        "last_run": {"number": live_run - 1, "bundles": len(before), "won": any(b.status == "won" for b in before),
                     "profit": round(sum(b.profit or 0 for b in before), 2)} if before else None,
    }
