"""API-Football (api-sports.io) client — fixtures, results, standings, H2H,
form and injuries.

Quota: the free plan is 100 requests/day and 10/minute. Every response carries
``x-ratelimit-requests-remaining`` / ``-limit`` headers, and ``/status`` reports
the day's usage without counting against it.

Quirk: API-Football returns HTTP 200 with an ``errors`` object when something
is wrong (bad key, season not on your plan, rate limit) — we turn that into a
ProviderError so it surfaces in the admin panel instead of looking like
"no data".
"""
import threading
import time

import httpx

from .base import ProviderError, ProviderNotConfigured, _int

BASE_URL = "https://v3.football.api-sports.io"

# Shared across instances so two syncs can't jointly break the per-minute limit.
_pace_lock = threading.Lock()
_last_call = 0.0


class ApiFootball:
    name = "api_football"

    def __init__(self, key: str, min_interval: float = 0.0, transport: httpx.BaseTransport | None = None):
        if not key:
            raise ProviderNotConfigured("API_FOOTBALL_KEY is not set")
        self.min_interval = min_interval
        self.client = httpx.Client(
            base_url=BASE_URL, headers={"x-apisports-key": key}, timeout=30, transport=transport
        )
        self.requests_made = 0
        self.remaining: int | None = None
        self.limit: int | None = None
        self._last_paging: dict | None = None

    def _pace(self):
        global _last_call
        if self.min_interval <= 0:
            return
        with _pace_lock:
            wait = _last_call + self.min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            _last_call = time.monotonic()

    def get(self, path: str, params: dict | None = None, *, counted: bool = True) -> list | dict:
        if counted:
            self._pace()
        try:
            r = self.client.get(path, params=params or {})
        except httpx.HTTPError as e:
            raise ProviderError(f"API-Football unreachable: {e}") from e
        if counted:
            self.requests_made += 1
        rem = _int(r.headers.get("x-ratelimit-requests-remaining"))
        lim = _int(r.headers.get("x-ratelimit-requests-limit"))
        if rem is not None:
            self.remaining, self.limit = rem, lim
        if r.status_code != 200:
            raise ProviderError(f"API-Football HTTP {r.status_code}: {r.text[:200]}")
        body = r.json()
        errors = body.get("errors")
        if errors:
            msg = "; ".join(f"{v}" for v in errors.values()) if isinstance(errors, dict) else "; ".join(map(str, errors))
            raise ProviderError(f"API-Football: {msg}")
        self._last_paging = body.get("paging")
        return body.get("response", [])

    # ── Endpoints ──

    def status(self) -> dict:
        """Account + today's usage. Free: does not count against the quota."""
        resp = self.get("/status", counted=False)
        reqs = (resp or {}).get("requests", {}) if isinstance(resp, dict) else {}
        sub = (resp or {}).get("subscription", {}) if isinstance(resp, dict) else {}
        used, limit = _int(reqs.get("current")), _int(reqs.get("limit_day"))
        return {
            "used": used,
            "limit": limit,
            "remaining": (limit - used) if used is not None and limit is not None else None,
            "plan": sub.get("plan"),
        }

    def fixtures(self, league: int, season: int) -> list:
        return self.get("/fixtures", {"league": league, "season": season})

    def standings(self, league: int, season: int) -> list:
        return self.get("/standings", {"league": league, "season": season})

    def head_to_head(self, home: int, away: int) -> list:
        return self.get("/fixtures/headtohead", {"h2h": f"{home}-{away}"})

    def team_fixtures(self, team: int, season: int) -> list:
        return self.get("/fixtures", {"team": team, "season": season})

    def injuries(self, fixture: int) -> list:
        return self.get("/injuries", {"fixture": fixture})

    # Pro-plan data. /odds is pre-match prices for every market the bookmakers
    # list, usually from ~2 weeks out; it's paged 10 fixtures at a time.

    def league_odds(self, league: int, season: int) -> list:
        items, page, total = [], 1, 1
        while page <= total:
            items += self.get("/odds", {"league": league, "season": season, "page": page})
            total = (self._last_paging or {}).get("total", 1)
            page += 1
        return items

    def fixture_odds(self, fixture: int) -> list:
        return self.get("/odds", {"fixture": fixture})

    def prediction(self, fixture: int) -> list:
        return self.get("/predictions", {"fixture": fixture})

    def team_statistics(self, league: int, season: int, team: int) -> dict:
        return self.get("/teams/statistics", {"league": league, "season": season, "team": team})

    def lineups(self, fixture: int) -> list:
        return self.get("/fixtures/lineups", {"fixture": fixture})
