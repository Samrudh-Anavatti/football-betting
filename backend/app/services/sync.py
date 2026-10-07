"""Data pulls: every provider call happens here, triggered from the admin panel.

Each button press creates a SyncRun row and then runs in a background thread
(API-Football's free plan allows 10 calls/minute, so a 12-league sync takes a
couple of minutes). The admin panel polls the run for progress. Set
SYNC_INLINE=1 to run synchronously (tests).
"""
import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .. import config
from ..database import SessionLocal
from ..models import Fixture, League, MarketBook, MatchContext, OddsSnapshot, ProviderQuota, SyncRun, Team
from ..providers.api_football import ApiFootball
from ..providers.base import ProviderError
from ..providers.odds_api import OddsApi
from .markets import filter_bookmakers, snapshots_from_book
from .matching import best_fixture_for_event
from .settlement import settle_fixture

log = logging.getLogger(__name__)

PROVIDERS = {
    "api_football": {
        "label": "API-Football",
        "site": "https://dashboard.api-football.com",
        "unit": "requests",
        "period": "per day",
        "feeds": "Fixtures, results, tables, research, and bookmaker prices for every market",
    },
    "odds_api": {
        "label": "The Odds API",
        "site": "https://the-odds-api.com/account/",
        "unit": "credits",
        "period": "per month",
        "feeds": "Backup price source: match result and total goals only",
    },
}

# Test seams: swap in clients with mocked transports.
def make_api_football() -> ApiFootball:
    return ApiFootball(config.API_FOOTBALL_KEY, config.API_FOOTBALL_MIN_INTERVAL)


def make_odds_api() -> OddsApi:
    return OddsApi(config.ODDS_API_KEY)


def configured(provider: str) -> bool:
    return bool(config.API_FOOTBALL_KEY if provider == "api_football" else config.ODDS_API_KEY)


def _utc_naive(iso: str) -> datetime:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


# ── Setup / bookkeeping ──────────────────────────────────────────────────────


def ensure_leagues(db: Session) -> None:
    """Upsert the league catalogue from config (names/keys may be edited there)."""
    for lg in config.LEAGUES:
        row = db.get(League, lg.id)
        if row is None:
            row = League(id=lg.id, season=config.FOOTBALL_SEASON)
            db.add(row)
        row.name, row.country, row.flag, row.odds_key = lg.name, lg.country, lg.flag, lg.odds_key
        row.season = config.FOOTBALL_SEASON
    db.commit()


def fail_interrupted_runs(db: Session) -> None:
    db.execute(
        update(SyncRun)
        .where(SyncRun.status == "running")
        .values(status="error", message="Interrupted by a server restart", finished_at=datetime.utcnow())
    )
    db.commit()


def save_quota(db: Session, provider: str, *, used=None, remaining=None, limit=None, plan=None, error=None) -> None:
    q = db.get(ProviderQuota, provider) or ProviderQuota(provider=provider)
    if remaining is not None:
        q.remaining = remaining
        q.used = used if used is not None else (limit - remaining if limit is not None else q.used)
        q.limit = limit if limit is not None else q.limit
    if plan:
        q.plan = plan
    q.last_error = error
    q.checked_at = datetime.utcnow()
    db.merge(q)
    db.commit()


def _save_client_quota(db: Session, client) -> None:
    if isinstance(client, ApiFootball) and client.remaining is not None:
        save_quota(db, "api_football", remaining=client.remaining, limit=client.limit)
    elif isinstance(client, OddsApi) and client.remaining is not None:
        save_quota(db, "odds_api", remaining=client.remaining, used=client.used,
                   limit=(client.remaining + client.used) if client.used is not None else None)


def check_quota(db: Session, provider: str) -> ProviderQuota:
    """Ask the provider for the current balance (free call on both)."""
    try:
        client = make_api_football() if provider == "api_football" else make_odds_api()
        s = client.status()
        save_quota(db, provider, used=s["used"], remaining=s["remaining"], limit=s["limit"], plan=s["plan"])
    except ProviderError as e:
        save_quota(db, provider, error=str(e))
    return db.get(ProviderQuota, provider)


def running_run(db: Session, provider: str) -> SyncRun | None:
    return db.scalar(select(SyncRun).where(SyncRun.provider == provider, SyncRun.status == "running"))


def start_run(db: Session, provider: str, kind: str, scope: str, total: int, user: str | None, job, *args) -> SyncRun:
    run = SyncRun(provider=provider, kind=kind, scope=scope, total=total, triggered_by=user)
    db.add(run)
    db.commit()
    run_id = run.id

    def _target():
        s = SessionLocal()
        try:
            job(s, s.get(SyncRun, run_id), *args)
        except Exception as e:  # last-resort: never leave a run stuck "running"
            log.exception("sync %s failed", run_id)
            s.rollback()
            r = s.get(SyncRun, run_id)
            r.status, r.message, r.finished_at = "error", f"Unexpected error: {e}", datetime.utcnow()
            s.commit()
        finally:
            s.close()

    if os.getenv("SYNC_INLINE") == "1":
        _target()
    else:
        threading.Thread(target=_target, daemon=True, name=f"sync-{run_id}").start()
    db.refresh(run)
    return run


def _finish(db: Session, run: SyncRun, client, errors: list[str], details: dict | None = None, message: str | None = None):
    run.requests_made = client.requests_made
    run.credits_used = getattr(client, "credits_used", client.requests_made)
    run.finished_at = datetime.utcnow()
    if errors and run.items == 0:
        run.status = "error"
    elif errors:
        run.status = "partial"
    else:
        run.status = "ok"
    run.message = message or ("; ".join(errors[:5]) if errors else None)
    if details is not None:
        run.details_json = json.dumps(details)
    db.commit()
    _save_client_quota(db, client)


# ── Fixtures, results & standings (API-Football) ─────────────────────────────


def _upsert_team(db: Session, t: dict) -> None:
    row = db.get(Team, t["id"])
    if row is None:
        db.add(Team(id=t["id"], name=t["name"], logo=t.get("logo")))
        db.flush()  # so the next fixture featuring this team finds it (autoflush is off)
    else:
        row.name, row.logo = t["name"], t.get("logo")


def upsert_fixture(db: Session, item: dict) -> Fixture:
    f, lg, teams = item["fixture"], item["league"], item["teams"]
    _upsert_team(db, teams["home"])
    _upsert_team(db, teams["away"])
    fx = db.get(Fixture, f["id"])
    if fx is None:
        fx = Fixture(id=f["id"])
        db.add(fx)
    fx.league_id, fx.season, fx.round = lg["id"], lg["season"], lg.get("round")
    fx.kickoff = _utc_naive(f["date"])
    fx.status, fx.status_long = f["status"]["short"], f["status"].get("long")
    fx.home_team_id, fx.away_team_id = teams["home"]["id"], teams["away"]["id"]
    ft = (item.get("score") or {}).get("fulltime") or {}
    goals = item.get("goals") or {}
    fx.home_goals = ft.get("home") if ft.get("home") is not None else goals.get("home")
    fx.away_goals = ft.get("away") if ft.get("away") is not None else goals.get("away")
    ht = (item.get("score") or {}).get("halftime") or {}
    fx.ht_home_goals, fx.ht_away_goals = ht.get("home"), ht.get("away")
    fx.venue = (f.get("venue") or {}).get("name")
    fx.updated_at = datetime.utcnow()
    db.flush()
    return fx


def _compact_standings(resp: list) -> list:
    out = []
    for block in resp:
        for group in block.get("league", {}).get("standings", []):
            for r in group:
                out.append({
                    "rank": r["rank"], "team_id": r["team"]["id"], "team": r["team"]["name"],
                    "logo": r["team"].get("logo"), "points": r["points"], "played": r["all"]["played"],
                    "gd": r["goalsDiff"], "form": r.get("form"), "group": r.get("group"),
                })
    return out


def job_fixtures(db: Session, run: SyncRun, league_ids: list[int], include_standings: bool) -> None:
    af = make_api_football()
    errors, per_league = [], {}
    for lid in league_ids:
        lg = db.get(League, lid)
        try:
            resp = af.fixtures(lid, lg.season)
            settled = 0
            for item in resp:
                fx = upsert_fixture(db, item)
                db.flush()
                settled += settle_fixture(db, fx)
            lg.fixtures_synced_at, lg.last_error = datetime.utcnow(), None
            if resp and resp[0]["league"].get("logo"):
                lg.logo = resp[0]["league"]["logo"]
            run.items += len(resp)
            per_league[lg.name] = {"fixtures": len(resp), "settled": settled}
            if include_standings:
                lg.standings_json = json.dumps(_compact_standings(af.standings(lid, lg.season)))
                lg.standings_synced_at = datetime.utcnow()
        except ProviderError as e:
            lg.last_error = str(e)
            errors.append(f"{lg.name}: {e}")
            per_league[lg.name] = {"error": str(e)}
        run.progress += 1
        run.requests_made = af.requests_made
        db.commit()
    _finish(db, run, af, errors, {"leagues": per_league})


# ── Odds (The Odds API) ──────────────────────────────────────────────────────

_MARKET_MAP = {"h2h": "1X2", "totals": "OU"}


def _snapshots_for_event(event: dict, fx: Fixture, pulled_at: datetime) -> list[OddsSnapshot]:
    rows = []
    for bm in event.get("bookmakers", []):
        bm_updated = _utc_naive(bm["last_update"]) if bm.get("last_update") else None
        for mk in bm.get("markets", []):
            market = _MARKET_MAP.get(mk["key"])
            if not market:
                continue
            for o in mk.get("outcomes", []):
                if market == "1X2":
                    sel = "home" if o["name"] == event["home_team"] else "away" if o["name"] == event["away_team"] else "draw"
                    line = None
                else:
                    sel, line = o["name"].lower(), o.get("point")
                rows.append(OddsSnapshot(
                    fixture_id=fx.id, pulled_at=pulled_at, bookmaker_key=bm["key"], bookmaker=bm["title"],
                    market=market, selection=sel, line=line, price=o["price"], bookmaker_updated_at=bm_updated,
                ))
    return rows


def ingest_odds_events(db: Session, lg: League, events: list[dict], pulled_at: datetime) -> tuple[int, list[str]]:
    """Match events to fixtures and store prices. Returns (matched, unmatched names)."""
    now = datetime.utcnow()
    candidates = list(db.scalars(
        select(Fixture).where(Fixture.league_id == lg.id, Fixture.kickoff >= now - timedelta(days=1),
                              Fixture.kickoff <= now + timedelta(days=60))
    ))
    matched, unmatched = 0, []
    for ev in events:
        fx = db.scalar(select(Fixture).where(Fixture.odds_event_id == ev["id"]))
        if fx is None:
            fx, _ = best_fixture_for_event(ev["home_team"], ev["away_team"], _utc_naive(ev["commence_time"]), candidates)
        if fx is None:
            unmatched.append(f"{ev['home_team']} v {ev['away_team']}")
            continue
        fx.odds_event_id, fx.odds_synced_at = ev["id"], pulled_at
        db.add_all(_snapshots_for_event(ev, fx, pulled_at))
        matched += 1
    return matched, unmatched


def job_odds(db: Session, run: SyncRun, league_ids: list[int], regions: list[str], markets: list[str]) -> None:
    api = make_odds_api()
    errors, per_league, all_unmatched = [], {}, []
    for lid in league_ids:
        lg = db.get(League, lid)
        try:
            events = api.odds(lg.odds_key, regions, markets)
            pulled_at = datetime.utcnow()
            matched, unmatched = ingest_odds_events(db, lg, events, pulled_at)
            lg.odds_synced_at = pulled_at
            run.items += matched
            per_league[lg.name] = {"events": len(events), "matched": matched, "unmatched": unmatched}
            all_unmatched += unmatched
        except ProviderError as e:
            errors.append(f"{lg.name}: {e}")
            per_league[lg.name] = {"error": str(e)}
        run.progress += 1
        run.requests_made, run.credits_used = api.requests_made, api.credits_used
        db.commit()
    note = None
    if all_unmatched and not errors:
        note = f"{len(all_unmatched)} bookmaker events had no matching fixture (sync fixtures first, or a team-name mismatch)."
    _finish(db, run, api, errors, {"leagues": per_league}, message=note)


def job_match_odds(db: Session, run: SyncRun, fixture_id: int, regions: list[str], markets: list[str]) -> None:
    api = make_odds_api()
    fx = db.get(Fixture, fixture_id)
    errors = []
    try:
        if fx.odds_event_id:
            ev = api.event_odds(fx.league.odds_key, fx.odds_event_id, regions, markets)
            events = [ev]
        else:  # not linked yet: pull the league and match it
            events = api.odds(fx.league.odds_key, regions, markets)
        pulled_at = datetime.utcnow()
        ingest_odds_events(db, fx.league, events, pulled_at)
        db.refresh(fx)
        run.items = 1 if fx.odds_synced_at == pulled_at else 0
        if not run.items:
            errors.append("No bookmaker prices found for this match yet")
    except ProviderError as e:
        errors.append(str(e))
    run.progress = 1
    db.commit()
    _finish(db, run, api, errors)


# ── All markets (API-Football /odds) ─────────────────────────────────────────


def ingest_market_items(db: Session, items: list[dict], pulled_at: datetime) -> int:
    """Store each fixture's book (our bookmakers only). Returns fixtures priced.
    Books freeze at kick-off: the last one before it is the closing book."""
    n = 0
    for item in items:
        fx = db.get(Fixture, item["fixture"]["id"])
        if fx is None or fx.kickoff <= pulled_at:
            continue
        books = filter_bookmakers(item.get("bookmakers", []), config.ODDS_BOOKMAKERS)
        if not books:
            continue
        db.merge(MarketBook(
            fixture_id=fx.id, provider="api_football", pulled_at=pulled_at,
            provider_updated_at=_utc_naive(item["update"]) if item.get("update") else None,
            bookmakers_json=json.dumps(books, separators=(",", ":")),
        ))
        db.add_all(snapshots_from_book(books, fx, pulled_at))
        fx.odds_synced_at = pulled_at
        n += 1
    return n


def job_markets(db: Session, run: SyncRun, league_ids: list[int]) -> None:
    af = make_api_football()
    errors, per_league = [], {}
    for lid in league_ids:
        lg = db.get(League, lid)
        try:
            items = af.league_odds(lid, lg.season)
            priced = ingest_market_items(db, items, datetime.utcnow())
            lg.odds_synced_at = datetime.utcnow()
            run.items += priced
            per_league[lg.name] = {"events": len(items), "matched": priced, "unmatched": []}
        except ProviderError as e:
            errors.append(f"{lg.name}: {e}")
            per_league[lg.name] = {"error": str(e)}
        run.progress += 1
        run.requests_made = af.requests_made
        db.commit()
    _finish(db, run, af, errors, {"leagues": per_league})


def job_match_markets(db: Session, run: SyncRun, fixture_id: int) -> None:
    af = make_api_football()
    errors = []
    try:
        run.items = ingest_market_items(db, af.fixture_odds(fixture_id), datetime.utcnow())
        if not run.items:
            errors.append("No prices from our bookmakers for this match yet (they usually appear 1 to 2 weeks before kick-off)")
    except ProviderError as e:
        errors.append(str(e))
    run.progress = 1
    db.commit()
    _finish(db, run, af, errors)


# ── Match context: H2H, form, injuries (API-Football) ────────────────────────


def _compact_match(item: dict) -> dict:
    ft = (item.get("score") or {}).get("fulltime") or {}
    g = item.get("goals") or {}
    return {
        "id": item["fixture"]["id"],
        "date": item["fixture"]["date"],
        "league": item["league"].get("name"),
        "home": item["teams"]["home"]["name"], "home_id": item["teams"]["home"]["id"],
        "away": item["teams"]["away"]["name"], "away_id": item["teams"]["away"]["id"],
        "hg": ft.get("home") if ft.get("home") is not None else g.get("home"),
        "ag": ft.get("away") if ft.get("away") is not None else g.get("away"),
        "status": item["fixture"]["status"]["short"],
    }


def _played(items: list[dict]) -> list[dict]:
    rows = [_compact_match(i) for i in items if i["fixture"]["status"]["short"] in ("FT", "AET", "PEN")]
    return sorted(rows, key=lambda m: m["date"], reverse=True)


def _form(team_id: int, rows: list[dict]) -> list[dict]:
    out = []
    for m in rows[:5]:
        is_home = m["home_id"] == team_id
        gf, ga = (m["hg"], m["ag"]) if is_home else (m["ag"], m["hg"])
        res = "W" if gf > ga else "L" if gf < ga else "D"
        out.append({**m, "venue": "H" if is_home else "A", "gf": gf, "ga": ga, "result": res})
    return out


def job_context(db: Session, run: SyncRun, fixture_id: int) -> None:
    af = make_api_football()
    fx = db.get(Fixture, fixture_id)
    ctx = db.get(MatchContext, fixture_id) or MatchContext(fixture_id=fixture_id)
    errors = {}

    def step(name, fn):
        try:
            fn()
            run.items += 1
        except ProviderError as e:
            errors[name] = str(e)
        run.progress += 1
        run.requests_made = af.requests_made
        db.commit()

    def h2h():
        ctx.h2h_json = json.dumps(_played(af.head_to_head(fx.home_team_id, fx.away_team_id))[:10])

    def form(team_id, attr):
        def _go():
            rows = _played(af.team_fixtures(team_id, fx.season))
            rows = [r for r in rows if r["date"] < fx.kickoff.isoformat()]
            if len(rows) < 5:  # early season: top up from last season
                rows += _played(af.team_fixtures(team_id, fx.season - 1))
            setattr(ctx, attr, json.dumps(_form(team_id, rows)))
        return _go

    def injuries():
        ctx.injuries_json = json.dumps([
            {"player": i["player"]["name"], "team_id": i["team"]["id"], "type": i["player"].get("type"),
             "reason": i["player"].get("reason")}
            for i in af.injuries(fx.id)
        ])

    def prediction():
        resp = af.prediction(fx.id)
        ctx.prediction_json = json.dumps(_compact_prediction(resp[0])) if resp else None

    def stats(team_id, attr):
        def _go():
            setattr(ctx, attr, json.dumps(_compact_team_stats(af.team_statistics(fx.league_id, fx.season, team_id))))
        return _go

    step("h2h", h2h)
    step("home_form", form(fx.home_team_id, "home_form_json"))
    step("away_form", form(fx.away_team_id, "away_form_json"))
    step("injuries", injuries)
    step("prediction", prediction)
    step("home_stats", stats(fx.home_team_id, "home_stats_json"))
    step("away_stats", stats(fx.away_team_id, "away_stats_json"))
    ctx.errors_json = json.dumps(errors) if errors else None
    ctx.fetched_at = datetime.utcnow()
    db.merge(ctx)
    db.commit()
    _finish(db, run, af, [f"{k}: {v}" for k, v in errors.items()])


CONTEXT_STEPS = 7


def _compact_prediction(p: dict) -> dict:
    pred = p.get("predictions") or {}
    return {
        "advice": pred.get("advice"),
        "winner": (pred.get("winner") or {}).get("name"),
        "win_or_draw": pred.get("win_or_draw"),
        "under_over": pred.get("under_over"),
        "goals": pred.get("goals"),
        "percent": pred.get("percent"),
        "comparison": p.get("comparison"),
    }


def _compact_team_stats(s: dict) -> dict:
    """Season stats for one team in this competition, home/away split."""
    if not s or not isinstance(s, dict):
        return {}
    g, fx = s.get("goals") or {}, s.get("fixtures") or {}

    def split(d):
        return {k: (d or {}).get(k) for k in ("home", "away", "total")}

    def by_minute(d):
        return {k: v.get("total") for k, v in (d or {}).items() if (v or {}).get("total")}

    cards = s.get("cards") or {}
    return {
        "form": s.get("form"),
        "played": split(fx.get("played")),
        "wins": split(fx.get("wins")),
        "draws": split(fx.get("draws")),
        "losses": split(fx.get("loses")),
        "goals_for": split((g.get("for") or {}).get("total")),
        "goals_against": split((g.get("against") or {}).get("total")),
        "goals_for_avg": split((g.get("for") or {}).get("average")),
        "goals_against_avg": split((g.get("against") or {}).get("average")),
        "goals_for_by_minute": by_minute((g.get("for") or {}).get("minute")),
        "goals_against_by_minute": by_minute((g.get("against") or {}).get("minute")),
        "clean_sheets": split(s.get("clean_sheet")),
        "failed_to_score": split(s.get("failed_to_score")),
        "biggest": s.get("biggest"),
        "penalty": s.get("penalty"),
        "formations": s.get("lineups"),
        "yellow_cards_by_minute": by_minute(cards.get("yellow")),
        "red_cards_by_minute": by_minute(cards.get("red")),
    }


def _lineup(t: dict) -> dict:
    def name(p):
        pl = p.get("player") or {}
        return f"{pl.get('name')} ({pl.get('pos')})" if pl.get("pos") else pl.get("name")

    return {
        "team_id": t["team"]["id"], "team": t["team"]["name"], "formation": t.get("formation"),
        "coach": (t.get("coach") or {}).get("name"),
        "start_xi": [name(p) for p in t.get("startXI", [])],
        "substitutes": [name(p) for p in t.get("substitutes", [])],
    }


def job_lineups(db: Session, run: SyncRun, fixture_id: int) -> None:
    af = make_api_football()
    ctx = db.get(MatchContext, fixture_id) or MatchContext(fixture_id=fixture_id)
    errors = []
    try:
        resp = af.lineups(fixture_id)
        ctx.lineups_json = json.dumps([_lineup(t) for t in resp]) if resp else None
        ctx.lineups_fetched_at = datetime.utcnow()
        run.items = 1 if resp else 0
        if not resp:
            errors.append("Line-ups aren't out yet (usually 20 to 40 minutes before kick-off)")
        db.merge(ctx)
    except ProviderError as e:
        errors.append(str(e))
    run.progress = 1
    db.commit()
    _finish(db, run, af, errors)
