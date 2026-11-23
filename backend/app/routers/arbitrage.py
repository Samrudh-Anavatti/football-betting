"""The arbitrage list for people outside the team: the same scan the AI Lab shows (see `services/arbitrage.py`).
An account gets the best few as a preview and how many more there are; members get the list (`access.FEATURES`)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import access
from ..database import get_db
from ..deps import require
from ..models import User
from ..services import arbitrage

router = APIRouter(prefix="/arbitrage", tags=["arbitrage"])


@router.get("")
def arbs(db: Session = Depends(get_db), user: User = Depends(require("arbitrage"))):
    out = arbitrage.overview(db)
    full = access.can(user, "arbitrage_full")
    shown = out["live"] if full else out["live"][:access.ARB_PREVIEW]
    return {**out, "live": shown, "more": len(out["live"]) - len(shown), "preview": not full}
