"""AI Lab (admins only): the AI staking test and the arbitrage scanner."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import admin_user
from ..models import Bundle
from ..serialize import tip_dict
from ..services import ai_staking, arbitrage
from ..services.staking import get_plan, plan_state
from .staking import PlanIn

router = APIRouter(prefix="/admin/ai-lab", tags=["ai-lab"], dependencies=[Depends(admin_user)])


def _state(db: Session) -> dict:
    return {
        **plan_state(db, ai_staking.SOURCE),
        "legs": ai_staking.leg_record(db),
        "open_legs": [{**tip_dict(t), "current_odds": price}
                      for t, price in ai_staking.open_legs(db, datetime.utcnow())],
    }


@router.get("/staking")
def staking(db: Session = Depends(get_db)):
    return _state(db)


@router.put("/staking/plan")
def update_plan(body: PlanIn, db: Session = Depends(get_db)):
    plan = get_plan(db, ai_staking.SOURCE)
    for k, v in body.model_dump().items():
        setattr(plan, k, v)
    db.commit()
    return _state(db)


@router.post("/staking/build")
def build(db: Session = Depends(get_db)):
    """Build the next bundle now rather than waiting for the schedule (which checks every minute)."""
    if ai_staking.build_bundle(db) is None:
        raise HTTPException(409, "No bundle: one is still live, or the open legs don't reach the target odds yet")
    return _state(db)


@router.delete("/staking/bundles/{bundle_id}", status_code=204)
def delete_bundle(bundle_id: int, db: Session = Depends(get_db)):
    b = db.get(Bundle, bundle_id)
    if b is None or b.plan_id != get_plan(db, ai_staking.SOURCE).id:
        raise HTTPException(404, "Bundle not found")
    if b.status != "pending":
        raise HTTPException(409, "Only a live bundle can be deleted")
    db.delete(b)
    db.commit()


@router.get("/arbs")
def arbs(db: Session = Depends(get_db)):
    return arbitrage.overview(db)
