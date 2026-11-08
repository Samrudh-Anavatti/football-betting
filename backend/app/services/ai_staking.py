"""The AI staking test (AI Lab): Ivo's staking plan run on the AI's bundle legs instead of his picks.

The AI records up to two short-priced, very likely legs per match (`ai_leg` tips, prompt v4). Whenever the AI plan
has no live bundle, `build_bundle` combines open legs into one at about the plan's target odds, with the plan's exact
recovery stake, and the usual settlement settles it. Plain code, no model call: the judgement per match is the AI's.
"""
import math
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..ai.service import LEG_MIN_ODDS
from ..models import Bundle, BundleLeg, Fixture, Tip
from .staking import get_plan, plan_bundles, run_state, stake_for
from .stats import current_price

SOURCE = "ai"
WINDOW = timedelta(hours=48)  # legs kicking off within this
LEAD = timedelta(minutes=30)  # and not sooner than this, so the bundle could really be placed
TOLERANCE = (0.9, 1.15)  # a bundle's odds may land this far either side of the target
MAX_LEGS = 8


def open_legs(db: Session, now: datetime) -> list[tuple[Tip, float | None]]:
    """Legs that could go in a bundle now, with the price each could be backed at, likeliest first."""
    q = (select(Tip).join(Fixture)
         .where(Tip.source == "ai_leg", Tip.status == "pending", Fixture.kickoff > now + LEAD,
                Fixture.kickoff <= now + WINDOW, Tip.id.not_in(select(BundleLeg.tip_id))))
    legs = [(t, current_price(db, t)) for t in db.scalars(q)]
    return sorted(legs, key=lambda x: (-(x[0].ai_probability or 0), x[0].fixture.kickoff))


def pick_legs(legs: list[tuple[Tip, float | None]], target: float) -> list[tuple[Tip, float]] | None:
    """The likeliest legs, one per match, until their combined odds reach the target; a leg that would overshoot
    too far is skipped for a shorter one. Skips legs whose price has drifted below the band or below the AI's own
    fair price (it would no longer be a leg). None if they can't get near the target."""
    lo, hi = target * TOLERANCE[0], target * TOLERANCE[1]
    chosen, matches, odds = [], set(), 1.0
    for tip, price in legs:
        if price is None or price < LEG_MIN_ODDS or price * (tip.ai_probability or 0) < 1:
            continue
        if tip.fixture_id in matches or odds * price > hi:
            continue
        chosen.append((tip, price))
        matches.add(tip.fixture_id)
        odds *= price
        if odds >= lo or len(chosen) == MAX_LEGS:
            break
    return chosen if chosen and odds >= lo else None


def build_bundle(db: Session, now: datetime | None = None) -> Bundle | None:
    """Make the AI plan's next bundle if it has none live and the open legs reach the target. Commits."""
    now = now or datetime.utcnow()
    plan = get_plan(db, SOURCE)
    rows = plan_bundles(db, plan)
    if any(b.status == "pending" for b in rows):
        return None  # the next stake depends on how the live one ends
    picked = pick_legs(open_legs(db, now), plan.target_odds)
    if picked is None:
        return None
    odds = round(math.prod(p for _, p in picked), 2)
    run = run_state(rows)
    bundle = Bundle(plan_id=plan.id, run=run["number"], step=run["step"], odds=odds,
                    stake=stake_for(plan, run["losses"], odds),
                    legs=[BundleLeg(tip_id=t.id, odds=p) for t, p in picked])
    db.add(bundle)
    db.commit()
    return bundle


def waiting_legs(db: Session, now: datetime) -> tuple[int, datetime | None]:
    """Legs for matches beyond the window: how many, and when the earliest comes into range (None if none)."""
    n, first = db.execute(select(func.count(), func.min(Fixture.kickoff)).select_from(Tip).join(Fixture)
                          .where(Tip.source == "ai_leg", Tip.status == "pending", Fixture.kickoff > now + WINDOW,
                                 Tip.id.not_in(select(BundleLeg.tip_id)))).one()
    return n, first - WINDOW if first else None


def leg_record(db: Session) -> dict:
    """How the AI's legs do on their own: hit rate against what their prices implied, and the AI's own estimate.
    The plan can only make money if legs land more often than their prices say."""
    legs = list(db.scalars(select(Tip).where(Tip.source == "ai_leg", Tip.status.in_(["won", "lost"]))))
    n = len(legs)
    won = sum(t.status == "won" for t in legs)
    return {
        "settled": n,
        "won": won,
        "hit_rate": round(won / n, 4) if n else None,
        "implied_rate": round(sum(1 / t.odds for t in legs) / n, 4) if n else None,  # includes the bookmakers' margin
        "ai_rate": round(sum(t.ai_probability or 0 for t in legs) / n, 4) if n else None,
        "profit_units": round(sum(t.odds - 1 if t.status == "won" else -1 for t in legs), 2),  # 1 unit on each
        "pending": db.scalar(select(func.count()).where(Tip.source == "ai_leg", Tip.status == "pending")),
    }
