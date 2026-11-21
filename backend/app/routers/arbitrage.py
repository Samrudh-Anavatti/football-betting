"""The arbitrage list for people outside the team: the same scan the AI Lab shows (see `services/arbitrage.py`),
for whoever has the `arbitrage` feature (see `access.FEATURES`)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require
from ..services import arbitrage

router = APIRouter(prefix="/arbitrage", tags=["arbitrage"])


@router.get("", dependencies=[Depends(require("arbitrage"))])
def arbs(db: Session = Depends(get_db)):
    return arbitrage.overview(db)
