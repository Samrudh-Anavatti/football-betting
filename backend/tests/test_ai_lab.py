"""AI Lab: the AI's bundle legs built into bundles on its own staking plan, separate from Ivo's."""
from datetime import timedelta
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import delete, select

from app.database import SessionLocal
from app.models import Bundle, BundleLeg, Fixture, Tip
from app.services import ai_staking

from .conftest import KICKOFF, af_fixture

API = "/api/v1"


def leg(fixture_id, prob, odds=None):
    return NS(fixture_id=fixture_id, ai_probability=prob, odds=odds)


def test_pick_legs():
    # Likeliest first, one per match, until about 6.00 (5.4 to 6.9).
    legs = [(leg(1, 0.9), 1.30), (leg(1, 0.85), 1.40), (leg(2, 0.8), 1.45), (leg(3, 0.78), 1.50), (leg(4, 0.75), 1.55),
            (leg(5, 0.72), 1.40)]
    picked = ai_staking.pick_legs(legs, 6.0)
    assert [t.fixture_id for t, _ in picked] == [1, 2, 3, 4, 5]
    # Skipped: a price that has drifted under 1.15, or under the AI's own fair price (0.8 x 1.2 < 1).
    assert ai_staking.pick_legs([(leg(1, 0.95), 1.12), (leg(2, 0.8), 1.2)], 1.1) is None
    # A leg that would overshoot (4.5 to 5.75 for a 5.00 target) is passed over for a shorter one.
    legs = [(leg(1, 0.9), 1.6), (leg(2, 0.9), 1.6), (leg(3, 0.9), 1.6), (leg(4, 0.85), 1.6), (leg(5, 0.86), 1.2)]
    assert [t.fixture_id for t, _ in ai_staking.pick_legs(legs, 5.0)] == [1, 2, 3, 5]  # 4.10 x 1.6 > 5.75; x 1.2 = 4.92
    assert ai_staking.pick_legs(legs[:2], 5.0) is None  # not enough yet


@pytest.fixture()
def lab_fixtures():
    """Six matches of our own; removed afterwards so the scheduler tests don't see them."""
    yield [2000 + i for i in range(6)]
    with SessionLocal() as db:
        ids = [2000 + i for i in range(6)]
        for b in db.scalars(select(Bundle).join(BundleLeg).join(Tip).where(Tip.fixture_id.in_(ids))).unique():
            db.delete(b)
        db.flush()
        db.execute(delete(Tip).where(Tip.fixture_id.in_(ids)))
        db.execute(delete(Fixture).where(Fixture.id.in_(ids)))
        db.commit()


def test_ai_staking_plan(client, auth, fake, monkeypatch, lab_fixtures):
    fake.af_fixtures = [af_fixture(2000 + i, (100 + i, f"Home {i}"), (200 + i, f"Away {i}"), KICKOFF) for i in range(6)]
    client.post(f"{API}/admin/sync/fixtures", json={"league_ids": [39], "include_standings": False}, headers=auth)
    monkeypatch.setattr(ai_staking, "current_price", lambda db, t: t.odds)
    with SessionLocal() as db:
        auto = 1  # any user
        ids = []
        for i, (odds, prob) in enumerate([(1.45, 0.8), (1.40, 0.82), (1.35, 0.85), (1.30, 0.88), (1.50, 0.75),
                                          (1.25, 0.9)]):
            t = Tip(fixture_id=2000 + i, author_id=auto, source="ai_leg", published=False, market="1X2",
                    selection="home", odds=odds, ai_probability=prob)
            db.add(t)
            db.flush()
            ids.append(t.id)
        db.commit()

        now = KICKOFF - timedelta(days=1)
        b = ai_staking.build_bundle(db, now)
        # 1.25 x 1.30 x 1.35 x 1.40 x 1.45 = 4.45, then 1.50 makes 6.68 (likeliest first).
        assert [leg.tip_id for leg in b.legs] == [ids[5], ids[3], ids[2], ids[1], ids[0], ids[4]]
        assert b.odds == 6.68 and b.stake == round(30 / 5.68, 2) and (b.run, b.step) == (1, 1)
        assert ai_staking.build_bundle(db, now) is None  # one live bundle at a time
        bundle_id = b.id

    s = client.get(f"{API}/admin/ai-lab/staking", headers=auth).json()
    assert s["current"]["id"] == bundle_id and s["legs"]["pending"] == 6 and s["open_legs"] == []
    assert client.get(f"{API}/staking", headers=auth).json()["current"] is None  # Ivo's plan is separate

    # A lost leg loses the bundle; the leg record counts each leg on its own.
    assert client.post(f"{API}/admin/tips/{ids[0]}/settle", headers=auth, json={"status": "lost"}).status_code == 200
    assert client.post(f"{API}/admin/tips/{ids[5]}/settle", headers=auth, json={"status": "won"}).status_code == 200
    s = client.get(f"{API}/admin/ai-lab/staking", headers=auth).json()
    assert s["current"] is None and s["history"][0]["status"] == "lost"
    assert s["run"]["step"] == 2 and s["run"]["next_stake"] == round((round(30 / 5.68, 2) + 30) / 5, 2)
    assert s["legs"]["settled"] == 2 and s["legs"]["won"] == 1 and s["legs"]["hit_rate"] == 0.5
    assert s["legs"]["implied_rate"] == round((1 / 1.45 + 1 / 1.25) / 2, 4) and s["legs"]["profit_units"] == -0.75

    # Settings are the AI plan's own; a live bundle can be deleted.
    r = client.put(f"{API}/admin/ai-lab/staking/plan", headers=auth, json={"base_stake": 2, "target_odds": 5, "bank": 100})
    assert r.json()["plan"]["base_stake"] == 2 and client.get(f"{API}/staking", headers=auth).json()["plan"]["base_stake"] == 6
    assert client.delete(f"{API}/admin/ai-lab/staking/bundles/{bundle_id}", headers=auth).status_code == 409


def test_ai_lab_is_admin_only(client):
    assert client.get(f"{API}/admin/ai-lab/staking").status_code == 401
