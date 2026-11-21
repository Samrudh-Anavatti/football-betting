"""Who sees what: visitors get the free few open picks, accounts get the rest, the staking plan and arbitrage."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import delete

from app.database import SessionLocal
from app.models import Fixture, Tip

from .conftest import KICKOFF, af_fixture
from .test_auth import signup

API = "/api/v1"


@pytest.fixture()
def pick_fixtures():
    """Five matches of our own, removed afterwards (other tests count what's in the database)."""
    ids = [5001 + i for i in range(5)]
    yield ids
    with SessionLocal() as db:
        db.execute(delete(Tip).where(Tip.fixture_id.in_(ids)))
        db.execute(delete(Fixture).where(Fixture.id.in_(ids)))
        db.commit()


def test_visitors_see_the_free_picks_only(client, auth, fake, pick_fixtures):
    fake.af_fixtures = [af_fixture(5001 + i, (50 + i, f"Home {i}"), (70 + i, f"Away {i}"), KICKOFF + timedelta(hours=i))
                        for i in range(5)]
    client.post(f"{API}/admin/sync/fixtures", json={"league_ids": [39], "include_standings": False}, headers=auth)
    ids = []
    for i, conf in enumerate([5, 9, 7, 8, 6]):
        r = client.post(f"{API}/admin/tips", headers=auth, json={
            "fixture_id": 5001 + i, "market": "1X2", "selection": "home", "odds": 1.8, "confidence": conf})
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])

    # A visitor: the three most confident, in kick-off order, and only the matches of the other two.
    assert [t["id"] for t in client.get(f"{API}/tips").json()] == [ids[1], ids[2], ids[3]]
    locked = client.get(f"{API}/tips/locked").json()
    assert [x["id"] for x in locked] == [ids[0], ids[4]]
    assert set(locked[0]) == {"id", "fixture"} and locked[0]["fixture"]["home"]["name"] == "Home 0"
    m = client.get(f"{API}/matches/5001").json()
    assert m["tips"] == [] and m["locked_tips"] == 1
    assert client.get(f"{API}/matches/5001/meta").json()["tips"] == []
    assert len(client.get(f"{API}/matches/5002").json()["tips"]) == 1

    # An account: all five, nothing locked, and it says so on /auth/me.
    h = signup(client, "picks@example.com")
    assert len(client.get(f"{API}/tips", headers=h).json()) == 5
    assert client.get(f"{API}/tips/locked", headers=h).json() == []
    m = client.get(f"{API}/matches/5001", headers=h).json()
    assert len(m["tips"]) == 1 and m["locked_tips"] == 0
    assert client.get(f"{API}/auth/me", headers=h).json()["access"] == {
        "all_picks": True, "ai_bets": True, "tonight": True, "tonight_custom": True, "staking": True, "arbitrage": True}

    # Once a match has kicked off its pick is on the record for everyone, and the next one becomes free.
    with SessionLocal() as db:
        db.get(Fixture, 5001).kickoff = datetime.utcnow() - timedelta(minutes=5)
        db.commit()
    assert ids[0] in [t["id"] for t in client.get(f"{API}/tips").json()]
    assert len(client.get(f"{API}/matches/5001").json()["tips"]) == 1


def test_accounts_get_the_staking_plan_and_arbitrage(client):
    assert client.get(f"{API}/staking").status_code == 401
    assert client.get(f"{API}/arbitrage").status_code == 401
    h = signup(client, "tools@example.com")
    assert client.get(f"{API}/staking", headers=h).status_code == 200
    r = client.get(f"{API}/arbitrage", headers=h)
    assert r.status_code == 200 and set(r.json()) == {"scanned_at", "live"}
    assert client.get(f"{API}/admin/ai-lab/arbs", headers=h).status_code == 403  # the lab itself stays the team's
