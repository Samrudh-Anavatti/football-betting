"""ORM → JSON dicts. Datetimes go out as ISO-8601 UTC with a trailing Z."""
import json
from datetime import datetime

from .models import Bet, Fixture, League, SyncRun, Tip


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") + "Z" if dt else None


def league_dict(lg: League) -> dict:
    return {
        "id": lg.id, "name": lg.name, "country": lg.country, "flag": lg.flag, "logo": lg.logo,
        "season": lg.season, "fixtures_synced_at": iso(lg.fixtures_synced_at),
        "odds_synced_at": iso(lg.odds_synced_at), "standings_synced_at": iso(lg.standings_synced_at),
        "last_error": lg.last_error,
    }


def team_dict(t) -> dict:
    return {"id": t.id, "name": t.name, "logo": t.logo}


def fixture_dict(fx: Fixture, best: dict | None = None) -> dict:
    return {
        "id": fx.id,
        "league": {"id": fx.league.id, "name": fx.league.name, "country": fx.league.country, "flag": fx.league.flag,
                   "logo": fx.league.logo},
        "round": fx.round,
        "kickoff": iso(fx.kickoff),
        "status": fx.status,
        "status_long": fx.status_long,
        "home": team_dict(fx.home_team),
        "away": team_dict(fx.away_team),
        "home_goals": fx.home_goals,
        "away_goals": fx.away_goals,
        "venue": fx.venue,
        "odds_synced_at": iso(fx.odds_synced_at),
        "best_1x2": best,
    }


def tip_dict(t: Tip, with_fixture: bool = True) -> dict:
    d = {
        "id": t.id, "fixture_id": t.fixture_id, "author": t.author.display_name, "market": t.market,
        "selection": t.selection, "line": t.line, "odds": t.odds, "bookmaker": t.bookmaker,
        "stake_units": t.stake_units, "confidence": t.confidence, "reasoning": t.reasoning,
        "published": t.published, "status": t.status, "profit_units": t.profit_units,
        "created_at": iso(t.created_at), "settled_at": iso(t.settled_at),
        "locked": t.fixture.kickoff <= datetime.utcnow(),
    }
    if with_fixture:
        d["fixture"] = fixture_dict(t.fixture)
    return d


def bet_dict(b: Bet) -> dict:
    return {
        "id": b.id, "user": b.user.display_name, "user_id": b.user_id, "tip_id": b.tip_id,
        "market": b.market, "selection": b.selection, "line": b.line, "odds": b.odds, "bookmaker": b.bookmaker,
        "stake": b.stake, "status": b.status, "profit": b.profit, "created_at": iso(b.created_at),
        "settled_at": iso(b.settled_at), "fixture": fixture_dict(b.fixture),
    }


def run_dict(r: SyncRun) -> dict:
    return {
        "id": r.id, "provider": r.provider, "kind": r.kind, "scope": r.scope, "status": r.status,
        "progress": r.progress, "total": r.total, "requests_made": r.requests_made, "credits_used": r.credits_used,
        "items": r.items, "message": r.message, "details": json.loads(r.details_json) if r.details_json else None,
        "triggered_by": r.triggered_by, "started_at": iso(r.started_at), "finished_at": iso(r.finished_at),
    }
