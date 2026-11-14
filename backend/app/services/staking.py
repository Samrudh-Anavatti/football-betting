"""The staking plan: where the current run stands, the stake for the next bundle, and settling bundles.

The stake is exact rather than a fixed ×1.2: (the run's losses so far + the target profit) ÷ (bundle odds − 1), so
a win always recovers the run whatever the bundle's odds. At the target odds that works out to multiplying by
odds ÷ (odds − 1) after each loss (×1.2 at 6.00).
"""
import math
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Bundle, StakingPlan
from ..serialize import iso, tip_dict


def get_plan(db: Session, source: str = "ivo") -> StakingPlan:
    plan = db.scalar(select(StakingPlan).where(StakingPlan.source == source))
    if plan is None:
        plan = StakingPlan(source=source)
        db.add(plan)
        db.commit()
    return plan


def target_profit(plan: StakingPlan) -> float:
    return round(plan.base_stake * (plan.target_odds - 1), 2)


def stake_for(plan: StakingPlan, losses: float, odds: float) -> float:
    return round((losses + target_profit(plan)) / (odds - 1), 2)


def plan_bundles(db: Session, plan: StakingPlan) -> list[Bundle]:
    return list(db.scalars(select(Bundle).where(Bundle.plan_id == plan.id).order_by(Bundle.id)))


def run_state(rows: list[Bundle]) -> dict:
    """The run the next bundle belongs to: its number, step, and what it has lost so far (settled bundles only)."""
    run, step, losses = 1, 1, 0.0
    for b in rows:
        if b.status == "won":
            run, step, losses = run + 1, 1, 0.0
        elif b.status == "lost":
            step, losses = step + 1, losses + b.stake
    return {"number": run, "step": step, "losses": round(losses, 2)}


def settled_odds(b: Bundle) -> float | None:
    """The bundle's odds as settled (void legs count at 1.00): 0 if a leg lost, None while still undecided."""
    statuses = [leg.tip.status for leg in b.legs]
    if "lost" in statuses:
        return 0.0
    if "pending" in statuses:
        return None
    return math.prod(leg.odds for leg in b.legs if leg.tip.status == "won")


def settle_bundles(db: Session) -> int:
    """Settle pending bundles whose legs have been decided. A lost leg settles the bundle straight away."""
    n = 0
    for b in db.scalars(select(Bundle).where(Bundle.status == "pending")):
        odds = settled_odds(b)
        if odds is None:
            continue
        if odds == 0:
            b.status, b.profit = "lost", -b.stake
        elif all(leg.tip.status == "void" for leg in b.legs):
            b.status, b.profit = "void", 0.0
        else:
            b.status, b.profit = "won", round(b.stake * (odds - 1), 2)
        b.settled_at = datetime.utcnow()
        n += 1
    from .tonight import settle as settle_sessions  # here, not at the top: tonight imports this module's helpers

    return n + settle_sessions(db)


def survivable_losses(plan: StakingPlan) -> int:
    """How many losses in a row the bank covers at the target odds."""
    lost, n = 0.0, 0
    while n < 100:
        lost += stake_for(plan, lost, plan.target_odds)
        if lost > plan.bank:
            return n
        n += 1
    return n


def bundle_dict(b: Bundle) -> dict:
    return {
        "id": b.id, "run": b.run, "step": b.step, "odds": b.odds, "bookmaker": b.bookmaker, "stake": b.stake, "status": b.status,
        "profit": b.profit, "returns": round(b.stake * b.odds, 2), "created_at": iso(b.created_at),
        "settled_at": iso(b.settled_at),
        "legs": [{"tip_id": leg.tip_id, "odds": leg.odds, "tip": tip_dict(leg.tip)} for leg in b.legs],
    }


def plan_state(db: Session, source: str = "ivo") -> dict:
    plan = get_plan(db, source)
    rows = plan_bundles(db, plan)
    run = run_state(rows)
    current = next((b for b in rows if b.status == "pending"), None)
    settled = [b for b in rows if b.status != "pending"]
    profit = round(sum(b.profit or 0 for b in settled), 2)
    streak = longest = 0
    for b in settled:
        if b.status == "lost":
            streak += 1
            longest = max(longest, streak)
        elif b.status == "won":
            streak = 0
    return {
        "plan": {"base_stake": plan.base_stake, "target_odds": plan.target_odds, "bank": plan.bank,
                 "target_profit": target_profit(plan), "multiplier": round(plan.target_odds / (plan.target_odds - 1), 4),
                 "survivable_losses": survivable_losses(plan), "started_at": iso(plan.created_at)},
        "run": {**run, "next_stake": stake_for(plan, run["losses"], plan.target_odds)},
        "current": bundle_dict(current) if current else None,
        "history": [bundle_dict(b) for b in reversed(settled)],
        "stats": {
            "bundles": len(settled), "won": sum(b.status == "won" for b in settled),
            "lost": sum(b.status == "lost" for b in settled), "runs_completed": run["number"] - 1,
            "profit": profit, "bank_now": round(plan.bank + profit, 2), "longest_losing_streak": longest,
        },
    }
