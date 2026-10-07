"""Track record (tips) and virtual bankrolls (bets)."""
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Bet, Fixture, MarketBook, OddsSnapshot, Tip, User
from .markets import best_price


def closing_price(db: Session, tip: Tip) -> float | None:
    """Best price in the last odds pull before kickoff — the market's final word."""
    fx: Fixture = tip.fixture
    if tip.market_id is not None:  # any board market: the frozen pre-kick-off book
        book = db.get(MarketBook, fx.id)
        if book is None or book.pulled_at <= tip.created_at or book.pulled_at > fx.kickoff:
            return None
        return best_price(json.loads(book.bookmakers_json), tip.market_id, tip.selection)
    last_pull = db.scalar(
        select(OddsSnapshot.pulled_at)
        .where(OddsSnapshot.fixture_id == fx.id, OddsSnapshot.pulled_at <= fx.kickoff)
        .order_by(OddsSnapshot.pulled_at.desc()).limit(1)
    )
    if last_pull is None or last_pull <= tip.created_at:
        return None  # no pull after the tip was placed, so nothing to compare
    q = select(OddsSnapshot.price).where(
        OddsSnapshot.fixture_id == fx.id, OddsSnapshot.pulled_at == last_pull,
        OddsSnapshot.market == tip.market, OddsSnapshot.selection == tip.selection,
    )
    if tip.line is not None:
        q = q.where(OddsSnapshot.line == tip.line)
    prices = list(db.scalars(q))
    return max(prices) if prices else None


def tip_record(db: Session, tips: list[Tip]) -> dict:
    settled = [t for t in tips if t.status in ("won", "lost", "void")]
    graded = [t for t in settled if t.status != "void"]
    staked = sum(t.stake_units for t in graded)
    profit = sum(t.profit_units or 0 for t in settled)
    won = sum(1 for t in graded if t.status == "won")
    clv = []
    for t in tips:
        cp = closing_price(db, t)
        if cp:
            clv.append(t.odds / cp - 1)
    return {
        "tips": len(tips),
        "pending": sum(1 for t in tips if t.status == "pending"),
        "won": won,
        "lost": sum(1 for t in graded if t.status == "lost"),
        "void": len(settled) - len(graded),
        "strike_rate": round(won / len(graded), 4) if graded else None,
        "units_staked": round(staked, 2),
        "profit_units": round(profit, 2),
        "roi": round(profit / staked, 4) if staked else None,
        "avg_odds": round(sum(t.odds for t in graded) / len(graded), 2) if graded else None,
        "clv": round(sum(clv) / len(clv), 4) if clv else None,
        "clv_samples": len(clv),
    }


def account_summary(db: Session, user: User) -> dict:
    bets = list(db.scalars(select(Bet).where(Bet.user_id == user.id)))
    settled = [b for b in bets if b.status != "pending"]
    open_ = [b for b in bets if b.status == "pending"]
    profit = sum(b.profit or 0 for b in settled)
    staked = sum(b.stake for b in settled if b.status != "void")
    exposure = sum(b.stake for b in open_)
    return {
        "user_id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "starting_bankroll": user.starting_bankroll,
        "balance": round(user.starting_bankroll + profit, 2),
        "available": round(user.starting_bankroll + profit - exposure, 2),
        "profit": round(profit, 2),
        "roi": round(profit / staked, 4) if staked else None,
        "open_bets": len(open_),
        "exposure": round(exposure, 2),
        "settled_bets": len(settled),
        "won": sum(1 for b in settled if b.status == "won"),
        "lost": sum(1 for b in settled if b.status == "lost"),
    }
