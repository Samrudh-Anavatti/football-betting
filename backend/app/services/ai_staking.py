"""The AI staking test (AI Lab): Ivo's staking plan run on the AI's bundle legs instead of his picks.

The AI records up to two short-priced, very likely legs per match (`ai_leg` tips, prompt v4). Whenever the AI plan
has no live bundle, `build_bundle` combines open legs into one at about the plan's target odds, priced at a single
bookmaker (a multi can't mix them), with the plan's exact recovery stake, and the usual settlement settles it. Plain code, no model call: the judgement per match is the AI's.
"""
import math
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..ai.service import LEG_MIN_ODDS
from ..models import Bundle, BundleLeg, Fixture, Tip
from .staking import get_plan, plan_bundles, run_state, stake_for
from .stats import current_prices

SOURCE = "ai"
WINDOW = timedelta(hours=48)  # legs kicking off within this
LEAD = timedelta(minutes=30)  # and not sooner than this, so the bundle could really be placed
TOLERANCE = (0.9, 1.15)  # a bundle's odds may land this far either side of the target
MAX_LEGS = 8


def open_legs(db: Session, now: datetime) -> list[tuple[Tip, dict[str, float]]]:
    """Legs that could go in a bundle now, with each bookmaker's price for them, likeliest first."""
    q = (select(Tip).join(Fixture)
         .where(Tip.source == "ai_leg", Tip.status == "pending", Fixture.kickoff > now + LEAD,
                Fixture.kickoff <= now + WINDOW, Tip.id.not_in(select(BundleLeg.tip_id))))
    legs = [(t, current_prices(db, t)) for t in db.scalars(q)]
    return sorted(legs, key=lambda x: (-(x[0].ai_probability or 0), x[0].fixture.kickoff))


def pick_legs(legs: list[tuple[Tip, float | None]], target: float, per_match: int = 1) -> list[tuple[Tip, float]] | None:
    """The likeliest legs, up to `per_match` from one match, until their combined odds reach the target; a leg that
    would overshoot too far is skipped for a shorter one. If that stops just short, one chosen leg is swapped for the
    likeliest unused leg that lifts the odds into the band. Skips legs whose price has drifted below the band or
    below the AI's own fair price (it would no longer be a leg). None if they can't get near the target."""
    lo, hi = target * TOLERANCE[0], target * TOLERANCE[1]
    usable = [(t, p) for t, p in legs if p is not None and p >= LEG_MIN_ODDS and p * (t.ai_probability or 0) >= 1]
    chosen, per, odds = [], Counter(), 1.0
    for tip, price in usable:
        if per[tip.fixture_id] >= per_match or odds * price > hi:
            continue
        chosen.append((tip, price))
        per[tip.fixture_id] += 1
        odds *= price
        if odds >= lo or len(chosen) == MAX_LEGS:
            break
    if chosen and odds < lo:
        taken = {id(t) for t, _ in chosen}
        swap, swap_key = None, None
        for i, (out, out_price) in reversed(list(enumerate(chosen))):  # the least likely chosen leg goes first
            for tip, price in usable:
                if id(tip) in taken or (tip.fixture_id != out.fixture_id and per[tip.fixture_id] >= per_match):
                    continue
                if lo <= odds / out_price * price <= hi and (swap_key is None or (tip.ai_probability or 0) > swap_key):
                    swap, swap_key = (i, tip, price), tip.ai_probability or 0
        if swap:
            i, tip, price = swap
            odds = odds / chosen[i][1] * price
            chosen[i] = (tip, price)
    return chosen if chosen and odds >= lo else None


def pick_bundle(legs: list[tuple[Tip, dict[str, float]]], target: float,
                per_match: int = 1) -> tuple[str, list[tuple[Tip, float]]] | None:
    """A multi is placed at one bookmaker, so build the bundle at each in turn with its own prices, and keep the one
    most likely to land (by the AI's probabilities), then the higher odds. None if no bookmaker reaches the target."""
    best, best_key = None, None
    for bookmaker in sorted({b for _, prices in legs for b in prices}):
        chosen = pick_legs([(t, prices.get(bookmaker)) for t, prices in legs], target, per_match)
        if chosen is None:
            continue
        key = (math.prod(t.ai_probability or 0 for t, _ in chosen), math.prod(p for _, p in chosen))
        if best_key is None or key > best_key:
            best, best_key = (bookmaker, chosen), key
    return best


def build_bundle(db: Session, now: datetime | None = None) -> Bundle | None:
    """Make the AI plan's next bundle if it has none live and the open legs reach the target. Commits."""
    now = now or datetime.utcnow()
    plan = get_plan(db, SOURCE)
    rows = plan_bundles(db, plan)
    if any(b.status == "pending" for b in rows):
        return None  # the next stake depends on how the live one ends
    found = pick_bundle(open_legs(db, now), plan.target_odds)
    if found is None:
        return None
    bookmaker, picked = found
    odds = round(math.prod(p for _, p in picked), 2)
    run = run_state(rows)
    bundle = Bundle(plan_id=plan.id, run=run["number"], step=run["step"], odds=odds, bookmaker=bookmaker,
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
