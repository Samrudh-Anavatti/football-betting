"""The refresh schedule: keeps results, prices, research and AI analyses fresh
without anyone pressing a button.

Two daemon threads inside the web process (B1 with Always On, one uvicorn
worker), each ticking once a minute:

* data: results, fixtures, odds, research and line-ups (API-Football);
* AI: one analysis at a time, since a model call takes a minute or so.

Supplementary leagues (config.LeagueDef) get fixtures, live scores and a 3-hourly
price sweep only: no near-kick-off prices, research, line-ups or AI analysis.

Every job works out what's due from the database (kick-off times and when each
thing was last fetched), so a restart or deploy simply picks up where it left
off. Each tick's work is one SyncRun per job, triggered_by "Schedule", so its
cost is in the history and on the Schedule card.

API-Football jobs stop for the day when the remaining allowance falls to the
reserve set on the Schedule card (results keep going: they're cheap and they
settle picks). Scheduled AI stops at AI_AUTO_BUDGET_SHARE of the monthly
budget, leaving the rest for the Analyse button.

Only one process runs the schedule at a time: a deploy briefly runs the old and
new app side by side, so each tick first renews a lease row in `settings`
(LEASE), and a second process waits until the first lets it lapse. Two
schedulers writing the same SQLite file over App Service's network share
corrupted the database's view of itself on 2026-10-12.

See HANDOFF.md → "Refresh schedule" for the costs.
"""
import logging
import os
import secrets
import socket
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from .. import config
from ..database import SessionLocal
from ..models import AiThread, Fixture, League, MarketBook, MatchContext, ProviderQuota, Setting, SyncRun, User
from ..providers.base import ProviderError
from ..serialize import run_dict
from . import sync
from .settlement import FINISHED, VOIDED

log = logging.getLogger(__name__)

UPCOMING = ("NS", "TBD")
FIXTURE_SLOTS = (6, 18)  # UTC hours for the full fixtures + tables sync
RESULTS_EVERY = timedelta(minutes=5)
ODDS_SWEEP_EVERY = timedelta(minutes=55)  # hourly, with slack for tick timing
SUPPLEMENTARY_ODDS_EVERY = timedelta(minutes=175)  # every 3 hours
NEAR_ODDS_WINDOW, NEAR_ODDS_EVERY = timedelta(hours=3), timedelta(minutes=15)
CLOSING_WINDOW, CLOSING_EVERY = timedelta(minutes=10), timedelta(minutes=5)
RESEARCH_WINDOW, RESEARCH_REFRESH = timedelta(days=7), timedelta(hours=24)
RESEARCH_PER_TICK = 10  # spreads a backlog (e.g. the first run) over a few minutes
LIGHT_WINDOW, LIGHT_EVERY = timedelta(hours=8), timedelta(hours=1)
LINEUPS_FROM, LINEUPS_UNTIL, LINEUPS_EVERY = timedelta(minutes=75), timedelta(minutes=15), timedelta(minutes=10)
AI_REFRESH_AT = timedelta(hours=6)
AI_RETRY_AFTER = timedelta(hours=1)
KEEP_RUNS = timedelta(days=14)
LEASE = timedelta(minutes=5)
INSTANCE = f"{socket.gethostname()}:{os.getpid()}:{secrets.token_hex(3)}"


@dataclass(frozen=True)
class Job:
    kind: str  # SyncRun.kind of its runs
    label: str
    cadence: str


JOBS = [
    Job("results", "Live scores and results", "Every 5 min while one of our matches is in play; settles picks at full time"),
    Job("fixtures", "Fixtures and tables", "06:00 and 18:00 UTC, all leagues including supplementary"),
    Job("markets", "Prices, all leagues", "Hourly; every 3 h for supplementary leagues (unchanged books add no history)"),
    Job("match_markets", "Prices near kick-off", "Main leagues: every 15 min in the last 3 h, plus a closing pull 5 to 10 min before"),
    Job("context", "Research", "Main leagues: when a match comes within 7 days, and again 24 h before"),
    Job("context_light", "Match-day research", "Main leagues: hourly from 8 h before, injuries and prediction"),
    Job("lineups", "Line-ups", "Main leagues: every 10 min from 75 min before until they're out"),
    Job("analysis", "AI analysis", "Main leagues: when a match comes within 7 days, and again 6 h before"),
]


# ── Settings (Admin → Data → Schedule) ──────────────────────────────────────


def get_settings(db: Session) -> dict:
    rows = {s.key: s.value for s in db.scalars(select(Setting).where(Setting.key.like("schedule_%")))}
    return {
        "enabled": rows.get("schedule_enabled", "1") == "1",
        "reserve": int(rows.get("schedule_reserve", config.SCHEDULE_RESERVE)),
    }


def save_settings(db: Session, enabled: bool | None = None, reserve: int | None = None) -> dict:
    if enabled is not None:
        db.merge(Setting(key="schedule_enabled", value="1" if enabled else "0"))
    if reserve is not None:
        db.merge(Setting(key="schedule_reserve", value=str(reserve)))
    db.commit()
    return get_settings(db)


# ── Helpers ─────────────────────────────────────────────────────────────────


def _api_allowance(db: Session, now: datetime) -> int | None:
    """Requests left today, refreshed (free) when we haven't checked since midnight UTC."""
    q = db.get(ProviderQuota, "api_football")
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if q is None or q.checked_at is None or q.checked_at < midnight:
        q = sync.check_quota(db, "api_football")
    return q.remaining if q else None


def _run(db: Session, kind: str, scope: str, total: int, job, *args, provider: str = "api_football") -> SyncRun:
    run = sync.start_run(db, provider, kind, scope, total, sync.AUTO, job, *args, inline=True)
    db.expire_all()  # the job wrote through its own session
    return run


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'es' if word.endswith('ch') else 's'}" if n != 1 else f"1 {word}"


def _batch(kind: str, fixtures: list[Fixture], work, db: Session) -> None:
    """One SyncRun for one job's fixtures this tick. work(af, fx) -> True if it got data."""
    if not fixtures:
        return
    ids = [f.id for f in fixtures]

    def job(s: Session, run: SyncRun):
        af = sync.make_api_football()
        errors, names = [], []
        for fid in ids:
            fx = s.get(Fixture, fid)
            try:
                if work(s, af, fx):
                    run.items += 1
                names.append(f"{fx.home_team.name} v {fx.away_team.name}")
            except ProviderError as e:
                errors.append(f"{fx.home_team.name} v {fx.away_team.name}: {e}")
            run.progress += 1
            run.requests_made = af.requests_made
            s.commit()
        sync._finish(s, run, af, errors, {"matches": names})

    _run(db, kind, _plural(len(ids), "match"), len(ids), job)


# ── Data jobs ───────────────────────────────────────────────────────────────


def due_results(db: Session, now: datetime) -> list[int]:
    """Kicked off in the last 12 hours and not finished (later stragglers are
    caught by the twice-daily fixtures sync)."""
    return list(db.scalars(select(Fixture.id).where(
        Fixture.kickoff <= now, Fixture.kickoff >= now - timedelta(hours=12),
        Fixture.status.not_in(FINISHED | VOIDED)).order_by(Fixture.kickoff)))


def due_fixture_leagues(db: Session, now: datetime) -> list[int]:
    slots = [now.replace(hour=h, minute=0, second=0, microsecond=0) for h in FIXTURE_SLOTS]
    slots += [s - timedelta(days=1) for s in slots]
    last_slot = max(s for s in slots if s <= now)
    return [lg.id for lg in db.scalars(select(League).order_by(League.id))
            if lg.fixtures_synced_at is None or lg.fixtures_synced_at < last_slot]


def due_odds_leagues(db: Session, now: datetime) -> list[int]:
    def every(lg):
        return SUPPLEMENTARY_ODDS_EVERY if lg.supplementary else ODDS_SWEEP_EVERY
    return [lg.id for lg in db.scalars(select(League).order_by(League.id))
            if lg.odds_synced_at is None or lg.odds_synced_at < now - every(lg)]


def _main_upcoming(now: datetime, window: timedelta):
    """Upcoming main-league fixtures kicking off within the window, soonest first."""
    return (select(Fixture).join(League).where(League.supplementary.is_(False), Fixture.status.in_(UPCOMING),
                                               Fixture.kickoff > now, Fixture.kickoff <= now + window)
            .order_by(Fixture.kickoff))


def due_near_odds(db: Session, now: datetime) -> list[Fixture]:
    out = []
    for fx in db.scalars(_main_upcoming(now, NEAR_ODDS_WINDOW)):
        every = CLOSING_EVERY if fx.kickoff - now <= CLOSING_WINDOW else NEAR_ODDS_EVERY
        last = db.scalar(select(MarketBook.pulled_at).where(MarketBook.fixture_id == fx.id))
        if (last is None or last <= now - every) and _attempt_ok(("odds", fx.id), now, every):
            out.append(fx)
    return out


def due_research(db: Session, now: datetime) -> list[Fixture]:
    out = []
    for fx in db.scalars(_main_upcoming(now, RESEARCH_WINDOW)):
        ctx = db.get(MatchContext, fx.id)
        stale = ctx is None or (fx.kickoff - now <= RESEARCH_REFRESH and ctx.fetched_at < fx.kickoff - RESEARCH_REFRESH)
        if stale and _attempt_ok(("research", fx.id), now, timedelta(hours=1)):
            out.append(fx)
        if len(out) == RESEARCH_PER_TICK:
            break
    return out


def due_light(db: Session, now: datetime) -> list[Fixture]:
    out = []
    for fx in db.scalars(_main_upcoming(now, LIGHT_WINDOW)):
        ctx = db.get(MatchContext, fx.id)
        if ctx is None:
            continue  # the full research job gets there first
        last = max(ctx.fetched_at, ctx.light_fetched_at or ctx.fetched_at)
        if last <= now - LIGHT_EVERY and _attempt_ok(("light", fx.id), now, LIGHT_EVERY):
            out.append(fx)
    return out


def due_lineups(db: Session, now: datetime) -> list[Fixture]:
    out = []
    for fx in db.scalars(select(Fixture).join(League).where(
            League.supplementary.is_(False), Fixture.kickoff > now - LINEUPS_UNTIL,
            Fixture.kickoff <= now + LINEUPS_FROM, Fixture.status.not_in(FINISHED | VOIDED))):
        ctx = db.get(MatchContext, fx.id)
        if ctx is not None and ctx.lineups_json:
            continue
        if _attempt_ok(("lineups", fx.id), now, LINEUPS_EVERY):
            out.append(fx)
    return out


# Per-match attempts, in memory: stops a match the provider has nothing for
# (no prices, no line-ups yet) from being asked again every minute.
_attempts: dict[tuple, datetime] = {}


def _attempt_ok(key: tuple, now: datetime, every: timedelta) -> bool:
    last = _attempts.get(key)
    if last is not None and last > now - every:
        return False
    _attempts[key] = now
    return True


def _fetch_odds(db: Session, af, fx: Fixture) -> bool:
    return bool(sync.ingest_market_items(db, af.fixture_odds(fx.id), datetime.utcnow()))


def _fetch_research(db: Session, af, fx: Fixture) -> bool:
    return not sync.fetch_context(db, af, fx)


def _fetch_light(db: Session, af, fx: Fixture) -> bool:
    return not sync.fetch_context(db, af, fx, light=True)


def _fetch_lineups(db: Session, af, fx: Fixture) -> bool:
    return sync.fetch_lineups(db, af, fx.id)


def data_tick(db: Session, now: datetime | None = None) -> None:
    """One pass over the data jobs, most urgent first."""
    now = now or datetime.utcnow()
    db.expire_all()
    if not sync.configured("api_football"):
        return
    left = _api_allowance(db, now)

    if ids := due_results(db, now):
        if left is None or left > 50:
            if _attempt_ok(("results",), now, RESULTS_EVERY):
                _run(db, "results", _plural(len(ids), "match") + " in play", (len(ids) + 19) // 20,
                     sync.job_results, ids)

    reserve = get_settings(db)["reserve"]

    def room() -> bool:
        remaining = db.get(ProviderQuota, "api_football")
        return remaining is None or remaining.remaining is None or remaining.remaining > reserve

    if not room():
        return
    if lids := due_fixture_leagues(db, now):
        _run(db, "fixtures", f"{_plural(len(lids), 'league')} + tables", len(lids), sync.job_fixtures, lids, True)
    if room() and (lids := due_odds_leagues(db, now)):
        _run(db, "markets", f"{_plural(len(lids), 'league')} · all markets", len(lids), sync.job_markets, lids)
    for kind, find, work in (
        ("match_markets", due_near_odds, _fetch_odds),
        ("context", due_research, _fetch_research),
        ("context_light", due_light, _fetch_light),
        ("lineups", due_lineups, _fetch_lineups),
    ):
        if not room():
            return
        _batch(kind, find(db, now), work, db)


# ── AI job ──────────────────────────────────────────────────────────────────


def auto_user(db: Session) -> User:
    """The author of scheduled analyses and their tips. It can't sign in (random
    password) and isn't listed under Accounts."""
    user = db.scalar(select(User).where(User.username == "auto"))
    if user is None:
        from ..security import hash_password

        user = User(username="auto", display_name="Auto", password_hash=hash_password(secrets.token_urlsafe(32)),
                    starting_bankroll=0)
        db.add(user)
        db.commit()
    return user


def due_analysis(db: Session, now: datetime) -> Fixture | None:
    """The next match to analyse: priced and researched, and either never
    analysed or last analysed before its 6-hours-out refresh."""
    q = (select(Fixture).join(MarketBook, MarketBook.fixture_id == Fixture.id)
         .join(MatchContext, MatchContext.fixture_id == Fixture.id).join(League)
         .where(League.supplementary.is_(False), Fixture.status.in_(UPCOMING), Fixture.kickoff > now + timedelta(minutes=15),
                Fixture.kickoff <= now + RESEARCH_WINDOW)
         .order_by(Fixture.kickoff))
    for fx in db.scalars(q):
        last = db.scalar(select(func.max(AiThread.created_at)).where(AiThread.fixture_id == fx.id))
        refresh_due = fx.kickoff - now <= AI_REFRESH_AT and (last is None or last < fx.kickoff - AI_REFRESH_AT)
        if (last is None or refresh_due) and _attempt_ok(("ai", fx.id), now, AI_RETRY_AFTER):
            return fx
    return None


def ai_tick(db: Session, now: datetime | None = None) -> None:
    from ..ai import client as ai_client
    from ..ai import service

    now = now or datetime.utcnow()
    db.expire_all()
    if not ai_client.configured():
        return
    if service.month_spend(db) >= config.AI_MONTHLY_BUDGET_USD * config.AI_AUTO_BUDGET_SHARE:
        return
    fx = due_analysis(db, now)
    if fx is None:
        return
    user = auto_user(db)
    thread = service.new_thread(db, fx, user)
    _run(db, "analysis", f"{fx.home_team.name} v {fx.away_team.name}", 1, service.job_turn, thread.id, user.id, True,
         provider="claude")


# ── Status for the Schedule card ────────────────────────────────────────────


def status(db: Session) -> dict:
    from ..ai import service

    now = datetime.utcnow()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today = {k: (n, r or 0) for k, n, r in db.execute(
        select(SyncRun.kind, func.count(), func.sum(SyncRun.requests_made))
        .where(SyncRun.triggered_by == sync.AUTO, SyncRun.started_at >= midnight).group_by(SyncRun.kind))}
    jobs = []
    for j in JOBS:
        last = db.scalar(select(SyncRun).where(SyncRun.triggered_by == sync.AUTO, SyncRun.kind == j.kind)
                         .order_by(SyncRun.id.desc()).limit(1))
        runs, requests = today.get(j.kind, (0, 0))
        jobs.append({"kind": j.kind, "label": j.label, "cadence": j.cadence, "runs_today": runs,
                     "requests_today": requests, "last_run": run_dict(last) if last else None})
    budget = config.AI_MONTHLY_BUDGET_USD
    return {
        **get_settings(db),
        "running": _threads_alive(),
        "jobs": jobs,
        "requests_today": sum(r for _, r in today.values() if r),
        "ai": {"spent_usd": service.month_spend(db), "limit_usd": budget,
               "auto_stops_at_usd": round(budget * config.AI_AUTO_BUDGET_SHARE, 2)},
    }


# ── Threads ─────────────────────────────────────────────────────────────────

_threads: list[threading.Thread] = []
_stop = threading.Event()


def _threads_alive() -> bool:
    return any(t.is_alive() for t in _threads)


def hold_lease(db: Session, now: datetime | None = None, instance: str = INSTANCE) -> bool:
    """Take or renew the schedule's lease; False while another process holds it.
    One UPDATE, so two processes can't both win."""
    now = now or datetime.utcnow()
    value = f"{instance}|{(now + LEASE).isoformat()}"
    db.execute(text("INSERT OR IGNORE INTO settings (key, value) VALUES ('schedule_lease', '|')"))
    won = db.execute(text(
        "UPDATE settings SET value = :value WHERE key = 'schedule_lease' "
        "AND (substr(value, 1, instr(value, '|') - 1) = :me OR substr(value, instr(value, '|') + 1) < :now)"),
        {"value": value, "me": instance, "now": now.isoformat()}).rowcount == 1
    db.commit()
    return won


def _loop(name: str, tick, every: float = 60) -> None:
    while not _stop.is_set():
        db = SessionLocal()
        try:
            if hold_lease(db) and get_settings(db)["enabled"]:
                tick(db)
        except Exception:  # keep the schedule alive; the run row (if any) has the details
            log.exception("scheduler %s tick failed", name)
            db.rollback()
        finally:
            db.close()
        _stop.wait(every)


def prune_runs(db: Session) -> None:
    db.execute(delete(SyncRun).where(SyncRun.triggered_by == sync.AUTO, SyncRun.started_at < datetime.utcnow() - KEEP_RUNS))
    db.commit()


def start() -> None:
    """Called at startup. One web worker only (see HANDOFF.md), so one schedule."""
    if config.SCHEDULER == "off" or _threads_alive():
        return
    db = SessionLocal()
    try:
        prune_runs(db)
    finally:
        db.close()
    _stop.clear()
    _threads[:] = [
        threading.Thread(target=_loop, args=("data", data_tick), daemon=True, name="schedule-data"),
        threading.Thread(target=_loop, args=("ai", ai_tick), daemon=True, name="schedule-ai"),
    ]
    for t in _threads:
        t.start()
