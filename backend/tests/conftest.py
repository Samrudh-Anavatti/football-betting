"""Test setup: throwaway SQLite, inline syncs, and fake provider responses."""
import os
import tempfile
from datetime import datetime, timedelta

os.environ["DATA_DIR"] = tempfile.mkdtemp()
os.environ["SYNC_INLINE"] = "1"
os.environ["API_FOOTBALL_KEY"] = "test"
os.environ["ODDS_API_KEY"] = "test"
os.environ["API_FOOTBALL_MIN_INTERVAL"] = "0"
os.environ["PASSWORD_IVO"] = "pw"

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config  # noqa: E402
from app.main import app  # noqa: E402
from app.providers.api_football import ApiFootball  # noqa: E402
from app.providers.odds_api import OddsApi  # noqa: E402
from app.services import sync  # noqa: E402

KICKOFF = (datetime.utcnow() + timedelta(days=2)).replace(microsecond=0)


def af_fixture(fid, home, away, kickoff, status="NS", hg=None, ag=None):
    return {
        "fixture": {"id": fid, "date": kickoff.isoformat() + "+00:00", "venue": {"name": "Ground"},
                    "status": {"short": status, "long": status}},
        "league": {"id": 39, "season": 2026, "round": "Regular Season - 7", "logo": "x.png"},
        "teams": {"home": {"id": home[0], "name": home[1]}, "away": {"id": away[0], "name": away[1]}},
        "goals": {"home": hg, "away": ag},
        "score": {"fulltime": {"home": hg, "away": ag}},
    }


class FakeProviders:
    """Mutable fake: tests edit `.af_fixtures` to simulate a result arriving."""

    def __init__(self):
        # Teams repeat across fixtures, as in a real season response.
        self.af_fixtures = [
            af_fixture(1001, (50, "Manchester City"), (39, "Wolves"), KICKOFF),
            af_fixture(1000, (39, "Wolves"), (50, "Manchester City"), KICKOFF - timedelta(days=60), "FT", 0, 2),
        ]
        self.calls = []

    def api_football(self, request: httpx.Request):
        self.calls.append(request.url.path)
        p = request.url.path
        headers = {"x-ratelimit-requests-remaining": "90", "x-ratelimit-requests-limit": "100"}
        if p == "/status":
            body = {"requests": {"current": 10, "limit_day": 100}, "subscription": {"plan": "Free"}}
        elif p == "/fixtures":
            body = self.af_fixtures
        elif p == "/standings":
            body = [{"league": {"standings": [[
                {"rank": 1, "team": {"id": 50, "name": "Manchester City"}, "points": 18, "all": {"played": 6}, "goalsDiff": 12},
                {"rank": 9, "team": {"id": 39, "name": "Wolves"}, "points": 8, "all": {"played": 6}, "goalsDiff": -1},
            ]]}}]
        elif p == "/fixtures/headtohead":
            body = [af_fixture(900, (39, "Wolves"), (50, "Manchester City"), KICKOFF - timedelta(days=200), "FT", 1, 3)]
        elif p == "/injuries":
            body = [{"player": {"name": "R. Dias", "type": "Missing Fixture", "reason": "Hamstring"}, "team": {"id": 50}}]
        else:
            return httpx.Response(404)
        return httpx.Response(200, json={"errors": [], "response": body}, headers=headers)

    def odds_api(self, request: httpx.Request):
        self.calls.append(request.url.path)
        headers = {"x-requests-remaining": "480", "x-requests-used": "20", "x-requests-last": "2"}
        if request.url.path.endswith("/sports"):
            return httpx.Response(200, json=[], headers={**headers, "x-requests-last": "0"})
        event = {
            "id": "evt1", "commence_time": KICKOFF.isoformat() + "Z",
            "home_team": "Manchester City", "away_team": "Wolverhampton Wanderers",
            "bookmakers": [
                {"key": "williamhill", "title": "William Hill", "last_update": KICKOFF.isoformat() + "Z", "markets": [
                    {"key": "h2h", "outcomes": [{"name": "Manchester City", "price": 1.4},
                                                {"name": "Wolverhampton Wanderers", "price": 7.5},
                                                {"name": "Draw", "price": 5.0}]},
                    {"key": "totals", "outcomes": [{"name": "Over", "price": 1.6, "point": 2.5},
                                                   {"name": "Under", "price": 2.3, "point": 2.5}]}]},
                {"key": "skybet", "title": "Sky Bet", "last_update": KICKOFF.isoformat() + "Z", "markets": [
                    {"key": "h2h", "outcomes": [{"name": "Manchester City", "price": 1.45},
                                                {"name": "Wolverhampton Wanderers", "price": 7.0},
                                                {"name": "Draw", "price": 4.8}]}]},
            ],
        }
        body = event if "/events/" in request.url.path else [event]
        return httpx.Response(200, json=body, headers=headers)


@pytest.fixture()
def fake(monkeypatch):
    f = FakeProviders()
    monkeypatch.setattr(sync, "make_api_football", lambda: ApiFootball("k", 0, transport=httpx.MockTransport(f.api_football)))
    monkeypatch.setattr(sync, "make_odds_api", lambda: OddsApi("k", transport=httpx.MockTransport(f.odds_api)))
    monkeypatch.setattr(config, "API_FOOTBALL_KEY", "k")
    monkeypatch.setattr(config, "ODDS_API_KEY", "k")
    return f


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth(client):
    r = client.post("/api/v1/auth/login", json={"username": "ivo", "password": "pw"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}
