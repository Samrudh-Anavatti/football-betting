"""Tonight's bundles: viewing sessions, the bundles built for one, and the record.

The sessions and the record are public (they're the shop window). Building bundles needs the `tonight` feature;
without `tonight_custom` as well, only the day's default request is answered, and with its first bundle only
(see `access.FEATURES`)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import access
from ..database import get_db
from ..deps import optional_user, require
from ..models import User
from ..serialize import iso
from ..services import tonight

router = APIRouter(prefix="/tonight", tags=["tonight"])


class BuildIn(BaseModel):
    session_at: datetime  # the session's first kick-off, as the sessions list gives it
    fixture_ids: list[int] = Field(min_length=1, max_length=40)
    target: float


@router.get("/sessions")
def sessions(db: Session = Depends(get_db), user: User | None = Depends(optional_user)):
    return {"sessions": tonight.sessions(db), "targets": tonight.TARGETS, "max_bundles": tonight.MAX_BUNDLES,
            "default": tonight.default_request(db), "custom": access.can(user, "tonight_custom")}


@router.post("/bundles")
def build(body: BuildIn, db: Session = Depends(get_db), user: User = Depends(require("tonight"))):
    if body.target not in tonight.TARGETS.values():
        raise HTTPException(422, "Pick one of the offered targets")
    at = body.session_at  # the list gives it as "...Z", so it arrives aware; the database is naive UTC
    session_at = at.astimezone(timezone.utc).replace(tzinfo=None) if at.tzinfo else at
    custom = access.can(user, "tonight_custom")
    if not custom:
        free = tonight.default_request(db)
        asked = (iso(session_at), sorted(set(body.fixture_ids)), body.target)
        if free is None or asked != (free["session_at"], sorted(free["fixture_ids"]), free["target"]):
            raise HTTPException(403, "Members only")
    bundles = tonight.build(db, session_at, body.fixture_ids, body.target, user_id=user.id)
    return {"bundles": [tonight.bundle_dict(b) for b in (bundles if custom else bundles[:1])]}


@router.get("/record")
def record(db: Session = Depends(get_db)):
    return tonight.record(db)
