"""AI Lab: the AI's bundle legs built into bundles on its own staking plan, separate from Ivo's."""
import json
from datetime import timedelta
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import delete, select

from app.database import SessionLocal
from app.models import ArbSighting, Bundle, BundleLeg, Fixture, MarketBook, Tip
from app.services import ai_staking, arbitrage

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
    # Stopping short of the band (1.3^4 = 2.86 for a 3.5 target, 3.15-4.03), it swaps a 1.3 for the 1.5: 3.29.
    legs = [(leg(i, 0.85), 1.3) for i in range(1, 5)] + [(leg(5, 0.7), 1.5)]
    assert [p for _, p in ai_staking.pick_legs(legs, 3.5)] == [1.3, 1.3, 1.3, 1.5]
    # Two legs from one match when allowed.
    assert len(ai_staking.pick_legs([(leg(1, 0.9), 1.5), (leg(1, 0.85), 1.5), (leg(2, 0.8), 1.5)], 3.3, per_match=2)) == 3


def test_pick_bundle_one_bookmaker():
    # The best price for each leg across books would reach 5.40-6.90 (1.6 x 1.6 x 1.6 x 1.4 = 5.73), but no single
    # bookmaker does: Bet365 3.84 (it doesn't price the fourth), Pinnacle 5.04.
    a, b, c, d = leg(1, 0.9), leg(2, 0.85), leg(3, 0.8), leg(4, 0.78)
    legs = [(a, {"Bet365": 1.6, "Pinnacle": 1.5}), (b, {"Bet365": 1.5, "Pinnacle": 1.6}),
            (c, {"Bet365": 1.6, "Pinnacle": 1.5}), (d, {"Pinnacle": 1.4})]
    assert ai_staking.pick_bundle(legs, 6.0) is None
    # With a fifth leg both can: Bet365 in four legs (6.14), Pinnacle in five (6.55). Fewer legs are likelier to land.
    legs.append((leg(5, 0.75), {"Bet365": 1.6, "Pinnacle": 1.3}))
    bookmaker, chosen = ai_staking.pick_bundle(legs, 6.0)
    assert bookmaker == "Bet365" and [t.fixture_id for t, _ in chosen] == [1, 2, 3, 5]
    assert [p for _, p in chosen] == [1.6, 1.5, 1.6, 1.6]


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
    monkeypatch.setattr(ai_staking, "current_prices", lambda db, t: {"Bet365": t.odds, "William Hill": t.odds - 0.05})
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

        # Three days out the legs are beyond the 48 h window: none can be bundled yet, usable from 48 h before.
        early = KICKOFF - timedelta(days=3)
        assert ai_staking.build_bundle(db, early) is None
        assert ai_staking.waiting_legs(db, early) == (6, KICKOFF - timedelta(hours=48))

        now = KICKOFF - timedelta(days=1)
        assert ai_staking.waiting_legs(db, now) == (0, None)  # all in range now
        b = ai_staking.build_bundle(db, now)
        # 1.25 x 1.30 x 1.35 x 1.40 x 1.45 = 4.45, then 1.50 makes 6.68 (likeliest first).
        assert [leg.tip_id for leg in b.legs] == [ids[5], ids[3], ids[2], ids[1], ids[0], ids[4]]
        assert b.bookmaker == "Bet365" and b.odds == 6.68 and b.stake == round(30 / 5.68, 2) and (b.run, b.step) == (1, 1)
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


def book(bid, name, over, under, over3=None, under3=None, dc=None):
    bets = [{"id": 5, "name": "Goals Over/Under", "values": [
        {"value": "Over 2.5", "odd": str(over)}, {"value": "Under 2.5", "odd": str(under)}]
        + ([{"value": "Over 3.0", "odd": str(over3)}, {"value": "Under 3.0", "odd": str(under3)}] if over3 else [])}]
    if dc:
        bets.append({"id": 12, "name": "Double Chance", "values": [
            {"value": "Home/Draw", "odd": str(dc[0])}, {"value": "Home/Away", "odd": str(dc[1])},
            {"value": "Draw/Away", "odd": str(dc[2])}]})
    return {"id": bid, "name": name, "bets": bets}


ARB_BOOKS = [book(8, "Bet365", 2.10, 1.75, 2.6, 1.6, (1.2, 1.3, 1.9)),
             book(4, "Pinnacle", 1.80, 2.05, 2.2, 1.75, (1.25, 1.35, 2.0))]


def test_find_arbs():
    arbs = arbitrage.find_arbs(ARB_BOOKS)
    # Over 2.5 at 2.10 (Bet365) + Under 2.5 at 2.05 (Pinnacle): 1/2.10 + 1/2.05 = 0.964, so 3.7% locked in.
    # Over/Under 3.0 is a whole line (pushes), and double chance outcomes overlap, so neither counts.
    assert len(arbs) == 1
    a = arbs[0]
    assert a["key"] == "5|2.5" and a["profit"] == round(1 / (1 / 2.10 + 1 / 2.05) - 1, 4) and not a["suspect"]
    assert [(leg["value"], leg["bookmaker"], leg["price"]) for leg in a["legs"]] == [
        ("Over 2.5", "Bet365", 2.10), ("Under 2.5", "Pinnacle", 2.05)]
    assert abs(a["legs"][0]["share"] * 2.10 - a["legs"][1]["share"] * 2.05) < 0.001  # same return either way
    assert arbitrage.find_arbs([book(8, "Bet365", 2.10, 1.75), book(4, "Pinnacle", 1.80, 1.85)]) == []  # 1.017


def test_arb_sightings(client, auth, fake):
    client.post(f"{API}/admin/sync/fixtures", json={"league_ids": [39], "include_standings": False}, headers=auth)
    t0 = KICKOFF - timedelta(days=1)
    with SessionLocal() as db:
        db.merge(MarketBook(fixture_id=1001, pulled_at=t0 - timedelta(minutes=1), provider_updated_at=t0,
                            bookmakers_json=json.dumps(ARB_BOOKS)))
        db.commit()
        arbitrage.scan(db, t0)
    live = client.get(f"{API}/admin/ai-lab/arbs", headers=auth).json()["live"]
    assert [(a["fixture"]["id"], a["market"], a["line"]) for a in live] == [(1001, "Goals Over/Under", 2.5)]

    # The next pull no longer shows it: closed at that pull.
    with SessionLocal() as db:
        db.merge(MarketBook(fixture_id=1001, pulled_at=t0 + timedelta(minutes=59), provider_updated_at=t0,
                            bookmakers_json=json.dumps([book(8, "Bet365", 1.9, 1.9), book(4, "Pinnacle", 1.9, 1.9)])))
        db.commit()
        arbitrage.scan(db, t0 + timedelta(hours=1))
    r = client.get(f"{API}/admin/ai-lab/arbs", headers=auth).json()
    assert r["live"] == [] and r["recent"][0]["gone_at"] is not None
    with SessionLocal() as db:
        db.execute(delete(ArbSighting))
        db.delete(db.get(MarketBook, 1001))
        db.commit()
