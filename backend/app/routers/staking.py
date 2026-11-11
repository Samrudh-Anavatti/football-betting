"""The staking plan and Ivo's bundle builder. Members can read it; only admins change it."""
import math
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import admin_user, member_user
from ..models import Bundle, BundleLeg, Tip
from ..services.staking import bundle_dict, get_plan, plan_bundles, plan_state, run_state, stake_for

router = APIRouter(prefix="/staking", tags=["staking"])


@router.get("", dependencies=[Depends(member_user)])
def state(db: Session = Depends(get_db)):
    return plan_state(db)


class PlanIn(BaseModel):
    base_stake: float = Field(gt=0)
    target_odds: float = Field(ge=1.5)
    bank: float = Field(gt=0)


@router.put("/plan", dependencies=[Depends(admin_user)])
def update_plan(body: PlanIn, db: Session = Depends(get_db)):
    plan = get_plan(db)
    for k, v in body.model_dump().items():
        setattr(plan, k, v)
    db.commit()
    return plan_state(db)


class BundleIn(BaseModel):
    tip_ids: list[int] = Field(min_length=1)
    stake: float | None = Field(None, gt=0)  # what was actually staked; defaults to the exact stake for this step


@router.post("/bundles", status_code=201, dependencies=[Depends(admin_user)])
def create_bundle(body: BundleIn, db: Session = Depends(get_db)):
    plan = get_plan(db)
    rows = plan_bundles(db, plan)
    if any(b.status == "pending" for b in rows):
        raise HTTPException(409, "The current bundle has to settle first: its result sets the next stake")
    tips = [db.get(Tip, i) for i in dict.fromkeys(body.tip_ids)]
    if any(t is None for t in tips):
        raise HTTPException(404, "Pick not found")
    now = datetime.utcnow()
    for t in tips:
        if t.source != "ivo" or not t.published or t.status != "pending" or t.fixture.kickoff <= now:
            raise HTTPException(409, "Only open, published picks that haven't kicked off can go in a bundle")
    if len({t.fixture_id for t in tips}) < len(tips):
        raise HTTPException(409, "Two picks from the same match can't go in one bundle")
    if db.scalars(select(BundleLeg).where(BundleLeg.tip_id.in_([t.id for t in tips]))).first():
        raise HTTPException(409, "One of these picks is already in a bundle")
    odds = round(math.prod(t.odds for t in tips), 2)
    if odds < 1.5:
        raise HTTPException(422, "The bundle's odds are too low to recover anything")
    run = run_state(rows)
    b = Bundle(plan_id=plan.id, run=run["number"], step=run["step"], odds=odds,
               stake=body.stake or stake_for(plan, run["losses"], odds),
               legs=[BundleLeg(tip_id=t.id, odds=t.odds) for t in tips])
    db.add(b)
    db.commit()
    db.refresh(b)
    return bundle_dict(b)


@router.delete("/bundles/{bundle_id}", status_code=204, dependencies=[Depends(admin_user)])
def delete_bundle(bundle_id: int, db: Session = Depends(get_db)):
    """Undo a bundle made by mistake. Settled bundles are the record and stay."""
    b = db.get(Bundle, bundle_id)
    if b is None:
        raise HTTPException(404, "Bundle not found")
    if b.status != "pending":
        raise HTTPException(409, "Settled bundles stay on the record")
    db.delete(b)
    db.commit()
