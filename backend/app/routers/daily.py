"""The bundle of the day: public (it's the site's free headline pick), with the spend and a build button for admins."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import admin_user
from ..models import AiCall, User
from ..serialize import iso, run_dict
from ..services import daily, sync

router = APIRouter(prefix="/daily", tags=["daily"])


@router.get("")
def today(db: Session = Depends(get_db)):
    return daily.state(db)


@router.get("/admin")
def admin(db: Session = Depends(get_db), _: User = Depends(admin_user)):
    """Each AI provider's month against its budget, and the last calls made for the bundle of the day."""
    calls = db.scalars(select(AiCall).order_by(AiCall.id.desc()).limit(20))
    return {
        "spend": daily.spend(db),
        "calls": [{"id": c.id, "provider": c.provider, "model": c.model, "day": c.day, "outcome": c.outcome,
                   "note": c.note, "input_tokens": c.input_tokens, "output_tokens": c.output_tokens,
                   "cost_usd": c.cost_usd, "created_at": iso(c.created_at)} for c in calls],
    }


@router.post("/build")
def build(db: Session = Depends(get_db), user: User = Depends(admin_user)):
    """Make today's bundle now, outside the schedule's hours (still one a day, and not while one is live)."""
    plan = daily.get_plan(db, daily.SOURCE)
    rows = daily.plan_bundles(db, plan)
    if any(b.status == "pending" for b in rows):
        raise HTTPException(409, "The last bundle hasn't settled yet: its result sets the next stake")
    if any(b.day == daily.day_of(daily.datetime.utcnow()) for b in rows):
        raise HTTPException(409, "Today's bundle is already made")
    if sync.running_run(db, "claude"):
        raise HTTPException(409, "The AI is already working on something; wait for it to finish")
    run = sync.start_run(db, "claude", "daily_bundle", "today", 1, user.display_name, daily.job)
    return run_dict(run)
