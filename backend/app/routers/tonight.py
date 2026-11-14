"""Tonight's bundles: viewing sessions, the bundles built for one, and the record.

Admins only while it's tested. The plan is: sessions and one bundle a day free to anyone signed in, the rest for
members (swap `admin_user` for that rule here, nothing else changes)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import admin_user
from ..models import User
from ..services import tonight

router = APIRouter(prefix="/tonight", tags=["tonight"])


class BuildIn(BaseModel):
    session_at: datetime  # the session's first kick-off, as the sessions list gives it
    fixture_ids: list[int] = Field(min_length=1, max_length=40)
    target: float


@router.get("/sessions")
def sessions(db: Session = Depends(get_db), user: User = Depends(admin_user)):
    return {"sessions": tonight.sessions(db), "targets": tonight.TARGETS, "max_bundles": tonight.MAX_BUNDLES}


@router.post("/bundles")
def build(body: BuildIn, db: Session = Depends(get_db), user: User = Depends(admin_user)):
    if body.target not in tonight.TARGETS.values():
        raise HTTPException(422, "Pick one of the offered targets")
    at = body.session_at  # the list gives it as "...Z", so it arrives aware; the database is naive UTC
    session_at = at.astimezone(timezone.utc).replace(tzinfo=None) if at.tzinfo else at
    bundles = tonight.build(db, session_at, body.fixture_ids, body.target, user_id=user.id)
    return {"bundles": [tonight.bundle_dict(b) for b in bundles]}


@router.get("/record")
def record(db: Session = Depends(get_db), user: User = Depends(admin_user)):
    return tonight.record(db)
