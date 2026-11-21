"""The bundle of the day: chosen by a model from the day's legs, checked in code, on its own capped staking run."""
from datetime import timedelta
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import delete, select

from app.ai import reviewer
from app.database import SessionLocal
from app.models import AiCall, Bundle, BundleLeg, Fixture, Tip
from app.services import daily

from .conftest import KICKOFF, af_fixture

API = "/api/v1"
IDS = [3000 + i for i in range(5)]
NOW = KICKOFF - timedelta(hours=3)


def test_run_resets_after_six_misses():
    lost = [NS(status="lost", stake=s) for s in (6, 7.2, 8.64, 10.37, 12.44)]
    assert daily.run_state(lost) == {"number": 1, "step": 6, "losses": 44.65}
    assert daily.run_state(lost + [NS(status="lost", stake=14.93)]) == {"number": 2, "step": 1, "losses": 0.0}
    assert daily.run_state(lost + [NS(status="won", stake=14.93)]) == {"number": 2, "step": 1, "losses": 0.0}


@pytest.fixture()
def legs(client, auth, fake, monkeypatch):
    """Five matches with one sure leg each at 1.50 (1.45 at William Hill); everything is removed afterwards."""
    fake.af_fixtures = [af_fixture(i, (300 + n, f"Home {n}"), (400 + n, f"Away {n}"), KICKOFF) for n, i in enumerate(IDS)]
    client.post(f"{API}/admin/sync/fixtures", json={"league_ids": [39], "include_standings": False}, headers=auth)
    monkeypatch.setattr(daily, "current_prices", lambda db, t: {"Bet365": t.odds, "William Hill": t.odds - 0.05})
    monkeypatch.setattr(reviewer, "configured", lambda provider: True)
    with SessionLocal() as db:
        tips = [Tip(fixture_id=i, author_id=1, source="ai_leg", published=False, market="1X2", selection="home",
                    odds=1.5, ai_probability=0.75, reasoning="Strong at home") for i in IDS]
        db.add_all(tips)
        db.commit()
        ids = [t.id for t in tips]
    yield ids
    with SessionLocal() as db:
        for b in db.scalars(select(Bundle).join(BundleLeg).join(Tip).where(Tip.fixture_id.in_(IDS))).unique():
            db.delete(b)
        db.flush()
        db.execute(delete(AiCall))
        db.execute(delete(Tip).where(Tip.fixture_id.in_(IDS)))
        db.execute(delete(Fixture).where(Fixture.id.in_(IDS)))
        db.commit()


def answer(ids, bookmaker="Bet365", **extra):
    return {"no_bundle": False, "reason_if_none": "", "bookmaker": bookmaker, "summary": "Five home sides.",
            "legs": [{"id": i, "reason": "At home and in form"} for i in ids], **extra}


def test_daily_bundle(client, auth, legs, monkeypatch):
    asked = []

    def ask(provider, system, user, schema):
        asked.append((provider, user))
        # The first answer is three legs, 1.5^3 = 3.38, under the band (5.10 to 7.50); the second is all five at
        # William Hill, 1.45^5 = 6.41.
        data = answer(legs[:3]) if len(asked) == 1 else answer(legs, "William Hill")
        return reviewer.Reply(data, provider, "claude-opus-5-5", 9000, 1500, 0.066)

    monkeypatch.setattr(reviewer, "ask", ask)
    assert client.get(f"{API}/daily").json()["bundle"] is None  # public, and empty before the first one
    with SessionLocal() as db:
        out = daily.build(db, NOW)
        assert out["status"] == "bundle" and out["model"] == "claude-opus-5-5"
        assert [p for p, _ in asked] == ["claude", "claude"] and "couldn't be used" in asked[1][1]
        calls = list(db.scalars(select(AiCall).order_by(AiCall.id)))
        assert [c.outcome for c in calls] == ["invalid", "bundle"] and "3.38" in calls[0].note
        assert daily.spend(db)["claude"]["spent_usd"] == 0.132
        assert not daily.due(db, NOW.replace(hour=9))  # one live bundle at a time

    s = client.get(f"{API}/daily").json()  # no sign-in needed
    b = s["bundle"]
    assert b["bookmaker"] == "William Hill" and b["odds"] == round(1.45 ** 5, 2) and b["by_claude"]
    assert b["stake"] == 6.0 and b["multiplier"] == 1.0 and (b["run"], b["step"]) == (1, 1)  # a first bet is the usual stake
    assert b["summary"] == "Five home sides." and b["legs"][0]["reason"] == "At home and in form"
    assert "author" not in b["legs"][0]["tip"]

    # A lost leg loses it; the next day's stake recovers it.
    assert client.post(f"{API}/admin/tips/{legs[0]}/settle", headers=auth, json={"status": "lost"}).status_code == 200
    s = client.get(f"{API}/daily").json()
    assert s["bundle"]["status"] == "lost" and s["run"]["misses"] == 1 and s["this_run"][0]["id"] == b["id"]
    assert s["run"]["next_stake"] == 7.2 and s["run"]["next_multiplier"] == 1.2  # 6 + the 6 lost ÷ (6.00 − 1)

    admin = client.get(f"{API}/daily/admin", headers=auth).json()
    assert admin["spend"]["claude"]["left_usd"] == 99.87 and len(admin["calls"]) == 2
    assert client.get(f"{API}/daily/admin").status_code == 401


def test_luna_stands_in_and_no_bundle(legs, monkeypatch):
    def ask(provider, system, user, schema):
        if provider == "claude":
            raise reviewer.ReviewError("Claude API error 529: overloaded")
        return reviewer.Reply({**answer([]), "no_bundle": True, "reason_if_none": "Too thin a day."}, provider,
                              "gpt-5.6-luna", 9000, 1000, 0.003)

    monkeypatch.setattr(reviewer, "ask", ask)
    with SessionLocal() as db:
        out = daily.build(db, NOW)
        assert out == {"status": "no_bundle", "message": "Too thin a day.", "cost_usd": 0.003}
        assert [(c.provider, c.outcome) for c in db.scalars(select(AiCall).order_by(AiCall.id))] == [
            ("claude", "error"), ("foundry", "no_bundle")]
        assert daily.state(db, NOW)["no_bundle_today"] == "Too thin a day."
        assert not daily.due(db, NOW.replace(hour=9))  # the day is decided
