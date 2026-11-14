"""Tonight's bundles: sessions from kick-off times, up to three bundles from different legs, settled on the record."""
from datetime import timedelta
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import delete, select

from app.database import SessionLocal
from app.models import Fixture, SessionBundle, SessionBundleLeg, Tip
from app.services import tonight

from .conftest import KICKOFF, af_fixture

API = "/api/v1"


def test_group_sessions():
    h = timedelta(hours=1)
    fx = [NS(id=i, kickoff=KICKOFF + d) for i, d in enumerate([0 * h, 2 * h, 2.5 * h, 3 * h, 26 * h, 27 * h])]
    groups = tonight.group_sessions(fx)
    # 15:00, 17:00 and 17:30 sit together (within 2 h 30 of the first); 18:00 starts a new session; next day its own.
    assert [[f.id for f in g] for g in groups] == [[0, 1, 2], [3], [4, 5]]


@pytest.fixture()
def night_fixtures():
    ids = [3000 + i for i in range(6)]
    yield ids
    with SessionLocal() as db:
        for b in db.scalars(select(SessionBundle).join(SessionBundleLeg).join(Tip).where(Tip.fixture_id.in_(ids))).unique():
            db.delete(b)
        db.flush()
        db.execute(delete(Tip).where(Tip.fixture_id.in_(ids)))
        db.execute(delete(Fixture).where(Fixture.id.in_(ids)))
        db.commit()


def test_tonight_bundles(client, auth, fake, monkeypatch, night_fixtures):
    ids = night_fixtures
    # Five matches tonight (four at 20:00, one at 20:45) and one tomorrow: one session of five, tomorrow's alone.
    times = [KICKOFF, KICKOFF, KICKOFF + timedelta(minutes=45)] * 2
    times[5] = KICKOFF + timedelta(days=1)
    fake.af_fixtures = [af_fixture(fid, (300 + i, f"Home {i}"), (400 + i, f"Away {i}"), times[i]) for i, fid in enumerate(ids)]
    client.post(f"{API}/admin/sync/fixtures", json={"league_ids": [39], "include_standings": False}, headers=auth)
    monkeypatch.setattr(tonight, "current_prices", lambda db, t: {"Bet365": t.odds, "William Hill": t.odds - 0.05})
    with SessionLocal() as db:
        tips = []
        for i, fid in enumerate(ids):
            for odds, prob in ([(1.45, 0.8), (1.30, 0.85)] if i < 5 else [(1.40, 0.8)]):
                t = Tip(fixture_id=fid, author_id=1, source="ai_leg", published=False, market="1X2" if odds > 1.4 else "OU",
                        selection="home" if odds > 1.4 else "over", line=None if odds > 1.4 else 2.5, odds=odds,
                        ai_probability=prob)
                db.add(t)
                tips.append(t)
        db.commit()
        now = KICKOFF - timedelta(hours=3)
        sessions = tonight.sessions(db, now)
        assert len(sessions) == 1  # tomorrow's single match can't make a session
        s = sessions[0]
        # Kick-off order, the 20:45 match last.
        assert [m["id"] for m in s["matches"]] == [ids[0], ids[1], ids[3], ids[4], ids[2]]
        assert s["legs"] == 10 and s["matches"][0]["legs"] == 2

        # Standard target over all five matches, each bundle at one bookmaker, within 5.40-6.90, from different legs.
        made = tonight.build(db, KICKOFF, ids[:5], 6.0, user_id=1, now=now)
        assert made and all(b.bookmaker == "Bet365" for b in made)
        assert all(5.4 <= b.odds <= 6.9 for b in made)
        legs_used = [leg.tip_id for b in made for leg in b.legs]
        assert len(legs_used) == len(set(legs_used))  # each bundle from different legs
        assert [b.position for b in made] == list(range(1, len(made) + 1))
        # The same request again returns the same bundles, not new ones.
        again = tonight.build(db, KICKOFF, ids[:5], 6.0, user_id=1, now=now)
        assert [b.id for b in again] == [b.id for b in made]
        # A different selection is a different request; tomorrow's match isn't in this session so it adds nothing.
        other = tonight.build(db, KICKOFF, ids[:3] + [ids[5]], 3.0, user_id=1, now=now)
        assert other and other[0].id not in {b.id for b in made} and all(2.7 <= b.odds <= 3.45 for b in other)
        assert all(leg.tip.fixture_id != ids[5] for b in other for leg in b.legs)
        assert not any(b.stretch for b in made + other)
        first = made[0]
        first_legs = [leg.tip_id for leg in first.legs]

        # A Big night on two matches: four sure legs make at most 1.45^2 x 1.30^2 = 3.55, so the AI's suggested bets
        # (longer shots) join in and the bundle is marked as a stretch. A suggested bet on the same selection as a
        # sure leg is the same bet and isn't used twice.
        for fid, odds, prob, market, sel in [(ids[0], 1.9, 0.58, "BTTS", "yes"), (ids[1], 1.6, 0.68, "BTTS", "yes"),
                                             (ids[1], 1.45, 0.75, "1X2", "home")]:
            db.add(Tip(fixture_id=fid, author_id=1, source="ai", published=False, market=market, selection=sel, odds=odds,
                       ai_probability=prob))
        db.commit()
        big = tonight.build(db, KICKOFF, ids[:2], 10.0, user_id=1, now=now)
        assert big and big[0].stretch and 9.0 <= big[0].odds <= 11.5
        srcs = [leg.tip.source for leg in big[0].legs]
        assert "ai" in srcs and "ai_leg" in srcs
        sels = [(leg.tip.fixture_id, leg.tip.market, leg.tip.selection) for leg in big[0].legs]
        assert len(sels) == len(set(sels))

    r = client.get(f"{API}/tonight/sessions", headers=auth)
    assert r.status_code == 200 and r.json()["targets"]["standard"] == 6.0 and len(r.json()["sessions"]) == 1
    r = client.post(f"{API}/tonight/bundles", headers=auth,
                    json={"session_at": s["at"], "fixture_ids": ids[:5], "target": 6.0})
    assert r.status_code == 200 and [b["id"] for b in r.json()["bundles"]] == [b.id for b in made]
    assert client.post(f"{API}/tonight/bundles", headers=auth,
                       json={"session_at": s["at"], "fixture_ids": ids[:5], "target": 4.0}).status_code == 422

    # Settlement: the first bundle's legs all win; a lost leg elsewhere loses its bundles. One unit each on the record.
    for tid in first_legs:
        assert client.post(f"{API}/admin/tips/{tid}/settle", headers=auth, json={"status": "won"}).status_code == 200
    rec = client.get(f"{API}/tonight/record", headers=auth).json()
    assert rec["won"] >= 1 and rec["profit_units"] >= round(first.odds - 1, 2) - 0.01
    assert rec["sessions"][0]["at"] == s["at"]
    assert rec["by_target"]["standard"]["won"] >= 1 and rec["by_target"]["big"]["bundles"] == 0
    assert rec["legs"]["sure"]["won"] == len(first_legs) and rec["legs"]["longer"]["settled"] == 0


def test_tonight_is_admin_only(client):
    assert client.get(f"{API}/tonight/sessions").status_code == 401
