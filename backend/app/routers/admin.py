"""Signed-in API: data integrations (sync buttons, quota), tips and virtual accounts."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..database import get_db
from ..deps import current_user
from ..models import Bet, Fixture, League, ProviderQuota, SyncRun, Tip, User
from ..security import make_token, verify_password
from ..serialize import bet_dict, iso, league_dict, run_dict, tip_dict
from ..services import sync
from ..services.settlement import MARKETS, apply_result, settle_fixture
from ..services.stats import account_summary, tip_record

auth_router = APIRouter(prefix="/auth", tags=["auth"])
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(current_user)])


# ── Auth ─────────────────────────────────────────────────────────────────────


class LoginIn(BaseModel):
    username: str
    password: str


def _me(u: User) -> dict:
    return {"id": u.id, "username": u.username, "display_name": u.display_name}


@auth_router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username.strip().lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Wrong username or password")
    return {"token": make_token(user.id), "user": _me(user)}


@auth_router.get("/me")
def me(user: User = Depends(current_user)):
    return _me(user)


# ── Integrations ─────────────────────────────────────────────────────────────


def _quota_dict(q: ProviderQuota | None) -> dict:
    if q is None:
        return {"used": None, "remaining": None, "limit": None, "plan": None, "checked_at": None, "last_error": None}
    return {"used": q.used, "remaining": q.remaining, "limit": q.limit, "plan": q.plan,
            "checked_at": iso(q.checked_at), "last_error": q.last_error}


@router.get("/integrations")
def integrations(db: Session = Depends(get_db)):
    """Everything the Data tab shows: providers, balances, costs, league freshness, recent runs."""
    providers = []
    for key, meta in sync.PROVIDERS.items():
        running = sync.running_run(db, key)
        last_runs = db.scalars(select(SyncRun).where(SyncRun.provider == key).order_by(SyncRun.id.desc()).limit(1))
        last = next(iter(last_runs), None)
        providers.append({
            "key": key, **meta,
            "configured": sync.configured(key),
            "quota": _quota_dict(db.get(ProviderQuota, key)),
            "running": run_dict(running) if running else None,
            "last_run": run_dict(last) if last else None,
        })
    return {
        "providers": providers,
        "leagues": [league_dict(lg) for lg in db.scalars(select(League).order_by(League.id.in_([2, 3]), League.country))],
        "odds_options": {"regions": config.ODDS_REGIONS, "markets": config.ODDS_MARKETS},
        "pacing_seconds": config.API_FOOTBALL_MIN_INTERVAL,
        "season": config.FOOTBALL_SEASON,
    }


@router.post("/integrations/{provider}/check")
def check(provider: str, db: Session = Depends(get_db)):
    if provider not in sync.PROVIDERS:
        raise HTTPException(404, "Unknown provider")
    return _quota_dict(sync.check_quota(db, provider))


@router.get("/sync-runs")
def sync_runs(limit: int = 30, db: Session = Depends(get_db)):
    return [run_dict(r) for r in db.scalars(select(SyncRun).order_by(SyncRun.id.desc()).limit(limit))]


@router.get("/sync-runs/{run_id}")
def sync_run(run_id: int, db: Session = Depends(get_db)):
    r = db.get(SyncRun, run_id)
    if r is None:
        raise HTTPException(404, "Run not found")
    return run_dict(r)


def _guard(db: Session, provider: str):
    if not sync.configured(provider):
        raise HTTPException(400, f"{sync.PROVIDERS[provider]['label']} isn't connected: add its API key in the App Service settings")
    if sync.running_run(db, provider):
        raise HTTPException(409, f"A {sync.PROVIDERS[provider]['label']} sync is already running, wait for it to finish")


def _leagues(db: Session, ids: list[int]) -> list[League]:
    rows = [db.get(League, i) for i in ids]
    if not rows or any(r is None for r in rows):
        raise HTTPException(400, "Pick at least one known league")
    return rows


class FixturesSyncIn(BaseModel):
    league_ids: list[int]
    include_standings: bool = True


@router.post("/sync/fixtures")
def sync_fixtures(body: FixturesSyncIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _guard(db, "api_football")
    lgs = _leagues(db, body.league_ids)
    scope = f"{len(lgs)} league{'s' * (len(lgs) != 1)}" + (" + standings" if body.include_standings else "")
    run = sync.start_run(db, "api_football", "fixtures", scope, len(lgs), user.display_name,
                         sync.job_fixtures, body.league_ids, body.include_standings)
    return run_dict(run)


class OddsSyncIn(BaseModel):
    league_ids: list[int]
    regions: list[str] = Field(default_factory=lambda: ["uk"])
    markets: list[str] = Field(default_factory=lambda: ["h2h"])

    @model_validator(mode="after")
    def _known(self):
        if not self.regions or not set(self.regions) <= set(config.ODDS_REGIONS):
            raise ValueError(f"regions must be from {config.ODDS_REGIONS}")
        if not self.markets or not set(self.markets) <= set(config.ODDS_MARKETS):
            raise ValueError(f"markets must be from {config.ODDS_MARKETS}")
        return self


@router.post("/sync/odds")
def sync_odds(body: OddsSyncIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _guard(db, "odds_api")
    lgs = _leagues(db, body.league_ids)
    scope = f"{len(lgs)} league{'s' * (len(lgs) != 1)} · {'+'.join(body.markets)} · {'+'.join(body.regions)}"
    run = sync.start_run(db, "odds_api", "odds", scope, len(lgs), user.display_name,
                         sync.job_odds, body.league_ids, body.regions, body.markets)
    return run_dict(run)


def _fixture(db: Session, fixture_id: int) -> Fixture:
    fx = db.get(Fixture, fixture_id)
    if fx is None:
        raise HTTPException(404, "Match not found")
    return fx


@router.post("/matches/{fixture_id}/context")
def refresh_context(fixture_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    fx = _fixture(db, fixture_id)
    _guard(db, "api_football")
    run = sync.start_run(db, "api_football", "context", f"{fx.home_team.name} v {fx.away_team.name}", 4,
                         user.display_name, sync.job_context, fixture_id)
    return run_dict(run)


@router.post("/matches/{fixture_id}/odds")
def refresh_match_odds(fixture_id: int, body: OddsSyncIn | None = None, db: Session = Depends(get_db),
                       user: User = Depends(current_user)):
    fx = _fixture(db, fixture_id)
    _guard(db, "odds_api")
    body = body or OddsSyncIn(league_ids=[fx.league_id], markets=["h2h", "totals"])
    run = sync.start_run(db, "odds_api", "match_odds", f"{fx.home_team.name} v {fx.away_team.name}", 1,
                         user.display_name, sync.job_match_odds, fixture_id, body.regions, body.markets)
    return run_dict(run)


# ── Tips ─────────────────────────────────────────────────────────────────────


class Selection(BaseModel):
    market: str
    selection: str
    line: float | None = None
    odds: float = Field(gt=1.0)
    bookmaker: str | None = None

    @model_validator(mode="after")
    def _valid(self):
        if self.market not in MARKETS or self.selection not in MARKETS[self.market]:
            raise ValueError(f"Unknown selection {self.market}/{self.selection}")
        if self.market == "OU" and self.line is None:
            raise ValueError("Over/under needs a goal line")
        if self.market != "OU":
            self.line = None
        return self


class TipIn(Selection):
    fixture_id: int
    stake_units: float = Field(1.0, gt=0, le=10)
    confidence: int = Field(3, ge=1, le=5)
    reasoning: str | None = None
    published: bool = True


class TipUpdate(BaseModel):
    odds: float | None = Field(None, gt=1.0)
    bookmaker: str | None = None
    stake_units: float | None = Field(None, gt=0, le=10)
    confidence: int | None = Field(None, ge=1, le=5)
    reasoning: str | None = None
    published: bool | None = None


class SettleIn(BaseModel):
    status: str = Field(pattern="^(won|lost|void|pending)$")


def _not_started(fx: Fixture):
    if fx.kickoff <= datetime.utcnow():
        raise HTTPException(409, "This match has kicked off, so its tips are locked")


@router.get("/tips")
def admin_tips(db: Session = Depends(get_db)):
    tips = list(db.scalars(select(Tip).join(Fixture).order_by(Fixture.kickoff.desc())))
    return {"tips": [tip_dict(t) for t in tips], "record": tip_record(db, tips)}


@router.post("/tips", status_code=201)
def create_tip(body: TipIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    fx = _fixture(db, body.fixture_id)
    _not_started(fx)
    tip = Tip(author_id=user.id, **body.model_dump())
    db.add(tip)
    db.commit()
    db.refresh(tip)
    return tip_dict(tip)


@router.put("/tips/{tip_id}")
def update_tip(tip_id: int, body: TipUpdate, db: Session = Depends(get_db)):
    tip = db.get(Tip, tip_id)
    if tip is None:
        raise HTTPException(404, "Tip not found")
    _not_started(tip.fixture)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(tip, k, v)
    db.commit()
    return tip_dict(tip)


@router.delete("/tips/{tip_id}", status_code=204)
def delete_tip(tip_id: int, db: Session = Depends(get_db)):
    tip = db.get(Tip, tip_id)
    if tip is None:
        raise HTTPException(404, "Tip not found")
    _not_started(tip.fixture)
    db.delete(tip)
    db.commit()


@router.post("/tips/{tip_id}/settle")
def settle_tip(tip_id: int, body: SettleIn, db: Session = Depends(get_db)):
    """Manual override for anything auto-settlement can't decide."""
    tip = db.get(Tip, tip_id)
    if tip is None:
        raise HTTPException(404, "Tip not found")
    if body.status == "pending":
        tip.status, tip.profit_units, tip.settled_at = "pending", None, None
    else:
        apply_result(tip, body.status, tip.stake_units)
    db.commit()
    return tip_dict(tip)


# ── Virtual accounts ─────────────────────────────────────────────────────────


class BetIn(Selection):
    fixture_id: int
    stake: float = Field(gt=0)
    tip_id: int | None = None


@router.get("/accounts")
def accounts(db: Session = Depends(get_db)):
    users = list(db.scalars(select(User).order_by(User.id)))
    bets = list(db.scalars(select(Bet).join(Fixture).order_by(Fixture.kickoff.desc()).limit(200)))
    return {"accounts": [account_summary(db, u) for u in users], "bets": [bet_dict(b) for b in bets]}


@router.post("/bets", status_code=201)
def create_bet(body: BetIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    fx = _fixture(db, body.fixture_id)
    _not_started(fx)
    bet = Bet(user_id=user.id, **body.model_dump())
    db.add(bet)
    db.commit()
    db.refresh(bet)
    return bet_dict(bet)


@router.delete("/bets/{bet_id}", status_code=204)
def delete_bet(bet_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    bet = db.get(Bet, bet_id)
    if bet is None or bet.user_id != user.id:
        raise HTTPException(404, "Bet not found")
    _not_started(bet.fixture)
    db.delete(bet)
    db.commit()


class BankrollIn(BaseModel):
    starting_bankroll: float = Field(gt=0)


@router.put("/accounts/me")
def set_bankroll(body: BankrollIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    user = db.get(User, user.id)
    user.starting_bankroll = body.starting_bankroll
    db.commit()
    return account_summary(db, user)


@router.post("/settle")
def settle_all(db: Session = Depends(get_db)):
    """Re-run auto-settlement over finished fixtures with pending tips/bets (no API calls)."""
    ids = set(db.scalars(select(Tip.fixture_id).where(Tip.status == "pending"))) | set(
        db.scalars(select(Bet.fixture_id).where(Bet.status == "pending")))
    n = sum(settle_fixture(db, db.get(Fixture, i)) for i in ids)
    db.commit()
    return {"settled": n}
