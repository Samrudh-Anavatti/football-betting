"""The Odds API (the-odds-api.com) client — bookmaker prices, no scraping.

Quota: credits per month (free = 500). A ``/odds`` call costs
``markets × regions`` credits per sport (nothing if the sport has no events).
Every response carries ``x-requests-remaining``, ``x-requests-used`` and
``x-requests-last`` (cost of that call). ``/sports`` is free, so we use it to
check the balance.
"""
import httpx

from .base import ProviderError, ProviderNotConfigured, _int

BASE_URL = "https://api.the-odds-api.com/v4"


class OddsApi:
    name = "odds_api"

    def __init__(self, key: str, transport: httpx.BaseTransport | None = None):
        if not key:
            raise ProviderNotConfigured("ODDS_API_KEY is not set")
        self.key = key
        self.client = httpx.Client(base_url=BASE_URL, timeout=30, transport=transport)
        self.requests_made = 0
        self.credits_used = 0
        self.remaining: int | None = None
        self.used: int | None = None

    def get(self, path: str, params: dict | None = None):
        try:
            r = self.client.get(path, params={"apiKey": self.key, **(params or {})})
        except httpx.HTTPError as e:
            raise ProviderError(f"The Odds API unreachable: {e}") from e
        self.requests_made += 1
        rem, used, last = (_int(r.headers.get(h)) for h in ("x-requests-remaining", "x-requests-used", "x-requests-last"))
        if rem is not None:
            self.remaining, self.used = rem, used
        self.credits_used += last or 0
        if r.status_code != 200:
            try:
                msg = r.json().get("message", r.text)
            except ValueError:
                msg = r.text
            raise ProviderError(f"The Odds API HTTP {r.status_code}: {msg[:200]}")
        return r.json()

    # ── Endpoints ──

    def status(self) -> dict:
        """Balance check via the free /sports endpoint."""
        self.get("/sports")
        limit = (self.remaining + self.used) if self.remaining is not None and self.used is not None else None
        return {"used": self.used, "remaining": self.remaining, "limit": limit, "plan": None}

    def odds(self, sport_key: str, regions: list[str], markets: list[str]) -> list:
        return self.get(
            f"/sports/{sport_key}/odds",
            {"regions": ",".join(regions), "markets": ",".join(markets), "oddsFormat": "decimal", "dateFormat": "iso"},
        )

    def event_odds(self, sport_key: str, event_id: str, regions: list[str], markets: list[str]) -> dict:
        return self.get(
            f"/sports/{sport_key}/events/{event_id}/odds",
            {"regions": ",".join(regions), "markets": ",".join(markets), "oddsFormat": "decimal", "dateFormat": "iso"},
        )
