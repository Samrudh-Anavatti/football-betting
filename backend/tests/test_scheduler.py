"""The refresh schedule: what each tick decides is due, what it spends, and that
it stops at the reserve and the AI budget share."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app import config
from app.ai import service
from app.database import SessionLocal
from app.models import AiThread, League, OddsSnapshot, ProviderQuota, Setting, SyncRun, Tip, User
from app.services import scheduler, sync

from .conftest import KICKOFF, af_fixture
from .test_ai import FakeModel, _connect

API = "/api/v1"


@pytest.fixture()
def db(client, fake):
    scheduler._attempts.clear()
    s = SessionLocal()
    for lg in s.scalars(select(League)):
        lg.fixtures_synced_at = lg.odds_synced_at = None
    s.commit()
    scheduler.save_settings(s, enabled=True, reserve=0)  # the fake provider only has 90 left
    yield s
    s.close()


def _kinds(db, since_id=0):
    return sorted(r.kind for r in db.scalars(select(SyncRun).where(SyncRun.id > since_id, SyncRun.triggered_by == sync.AUTO)))


def _last_id(db):
    return db.scalar(select(func.max(SyncRun.id))) or 0


def test_first_tick_syncs_everything_then_rests(db, fake):
    scheduler.data_tick(db)
    # Every league's fixtures + tables and prices, research for the match 2 days out.
    assert _kinds(db) == ["context", "fixtures", "markets"]
    research = db.scalar(select(SyncRun).where(SyncRun.kind == "context"))
    assert research.items == 1 and research.requests_made == 10 and research.status == "ok"

    mark, snapshots = _last_id(db), db.scalar(select(func.count(OddsSnapshot.id)))
    scheduler.data_tick(db)
    assert _kinds(db, mark) == []  # nothing due a minute later

    # An hour later the sweep runs again, but an unchanged book adds no history.
    scheduler.data_tick(db, datetime.utcnow() + timedelta(minutes=61))
    assert _kinds(db, mark) == ["markets"]
    assert db.scalar(select(func.count(OddsSnapshot.id))) == snapshots


def test_match_day_jobs(db, fake):
    scheduler.data_tick(db)
    mark = _last_id(db)
    # 50 minutes before kick-off: the 24-hours-out research, near-kick-off prices, the light
    # research refresh and line-ups (plus the fixtures and odds sweeps, two days on).
    scheduler.data_tick(db, KICKOFF - timedelta(minutes=50))
    assert _kinds(db, mark) == ["context", "context_light", "fixtures", "lineups", "markets", "match_markets"]
    light = db.scalar(select(SyncRun).where(SyncRun.kind == "context_light"))
    assert light.requests_made == 2 and light.status == "ok"
    # Line-ups are in, so they aren't asked for again.
    mark = _last_id(db)
    scheduler.data_tick(db, KICKOFF - timedelta(minutes=30))
    assert "lineups" not in _kinds(db, mark)


def test_results_settle_at_full_time(client, auth, db, fake):
    started = datetime.utcnow().replace(microsecond=0) - timedelta(minutes=100)
    fake.af_fixtures = [af_fixture(1001, (50, "Manchester City"), (39, "Wolves"), started, "2H", 1, 0)]
    scheduler.data_tick(db)
    db.add(Tip(fixture_id=1001, author_id=db.scalar(select(User.id).where(User.username == "ivo")),
               market="1X2", selection="home", odds=1.5, stake_units=2))
    db.commit()

    fake.af_fixtures = [af_fixture(1001, (50, "Manchester City"), (39, "Wolves"), started, "FT", 2, 0)]
    fake.calls.clear()
    scheduler.data_tick(db, datetime.utcnow() + timedelta(minutes=6))
    run = db.scalar(select(SyncRun).where(SyncRun.kind == "results").order_by(SyncRun.id.desc()))
    assert run.details_json and '"settled": 1' in run.details_json and "Premier League" in run.details_json
    assert fake.calls.count("/standings") == 1  # the finished match's table
    tip = db.scalar(select(Tip).where(Tip.fixture_id == 1001))
    db.refresh(tip)
    assert tip.status == "won" and tip.profit_units == 1.0


def test_reserve_stops_everything_but_results(db, fake):
    scheduler.save_settings(db, reserve=100)  # above the 90 left
    scheduler.data_tick(db)
    assert _kinds(db) == []
    q = db.get(ProviderQuota, "api_football")
    assert q.remaining == 90


def test_scheduled_runs_stay_out_of_the_buttons_way(client, auth, db, fake):
    scheduler.data_tick(db)
    assert client.get(f"{API}/admin/sync-runs", headers=auth).json() == []
    assert len(client.get(f"{API}/admin/sync-runs?scheduled=true", headers=auth).json()) == 3
    s = client.get(f"{API}/admin/schedule", headers=auth).json()
    jobs = {j["kind"]: j for j in s["jobs"]}
    n = len(config.LEAGUES)
    assert jobs["fixtures"]["requests_today"] == 2 * n and jobs["context"]["runs_today"] == 1
    assert s["requests_today"] == 2 * n + n + 10 and s["reserve"] == 0
    s = client.put(f"{API}/admin/schedule", headers=auth, json={"enabled": False, "reserve": 1500}).json()
    assert s["enabled"] is False and s["reserve"] == 1500


def test_ai_analyses_once_then_six_hours_out(db, fake, monkeypatch):
    model = FakeModel()
    monkeypatch.setattr(service, "make_client", lambda: model)
    _connect(monkeypatch)
    scheduler.data_tick(db)

    scheduler.ai_tick(db)
    thread = db.scalar(select(AiThread))
    assert thread.created_by == "Auto"
    tips = list(db.scalars(select(Tip).where(Tip.source == "ai")))
    assert tips and all(t.author.username == "auto" and not t.published for t in tips)

    scheduler.ai_tick(db)
    assert db.scalar(select(func.count(AiThread.id))) == 1  # not due again until 6 h out

    scheduler.ai_tick(db, KICKOFF - timedelta(hours=5))
    assert db.scalar(select(func.count(AiThread.id))) == 2

    # Spend at the auto share of the budget: scheduled analyses stop.
    monkeypatch.setattr(config, "AI_MONTHLY_BUDGET_USD", 0.001)
    scheduler._attempts.clear()
    scheduler.ai_tick(db, KICKOFF - timedelta(hours=1))
    assert db.scalar(select(func.count(AiThread.id))) == 2


def test_auto_user_is_not_an_account(client, auth, db):
    scheduler.auto_user(db)
    names = [a["username"] for a in client.get(f"{API}/admin/accounts", headers=auth).json()["accounts"]]
    assert "auto" not in names
    assert client.post(f"{API}/auth/login", json={"username": "auto", "password": ""}).status_code == 401


def test_supplementary_leagues_get_data_but_no_research_or_ai(client, db, fake, monkeypatch):
    model = FakeModel()
    monkeypatch.setattr(service, "make_client", lambda: model)
    _connect(monkeypatch)
    fake.af_fixtures = [af_fixture(2001, (60, "Leeds"), (61, "Hull"), KICKOFF, league=40)]
    scheduler.data_tick(db)
    assert {"fixtures", "markets"} <= set(_kinds(db))
    researched = [r.details_json for r in db.scalars(select(SyncRun).where(SyncRun.kind == "context"))]
    assert not any("Leeds" in (d or "") for d in researched)  # no research for a Championship match
    scheduler._attempts.clear()
    scheduler.ai_tick(db)
    assert db.scalar(select(func.count(AiThread.id)).where(AiThread.fixture_id == 2001)) == 0

    # Supplementary prices every 3 hours, main hourly.
    mark = _last_id(db)
    scheduler.data_tick(db, datetime.utcnow() + timedelta(minutes=61))
    run = db.scalar(select(SyncRun).where(SyncRun.id > mark, SyncRun.kind == "markets"))
    assert run.total == sum(1 for lg in config.LEAGUES if not lg.supplementary)

    # Kept off the home page's lists, shown under "more leagues".
    assert 2001 not in [f["id"] for f in client.get(f"{API}/fixtures", params={"tier": "main"}).json()]
    more = client.get(f"{API}/fixtures", params={"tier": "more"}).json()
    assert [f["id"] for f in more] == [2001]
    lg = next(x for x in client.get(f"{API}/leagues").json() if x["id"] == 40)
    assert lg["supplementary"] is True


def test_only_one_process_runs_the_schedule(db):
    now = datetime.utcnow()
    db.execute(Setting.__table__.delete().where(Setting.key == "schedule_lease"))
    db.commit()
    assert scheduler.hold_lease(db, now, instance="old")
    assert not scheduler.hold_lease(db, now + timedelta(minutes=1), instance="new")  # deploy overlap
    assert scheduler.hold_lease(db, now + timedelta(minutes=1), instance="old")  # renews
    assert scheduler.hold_lease(db, now + timedelta(minutes=7), instance="new")  # old one gone quiet
    assert not scheduler.hold_lease(db, now + timedelta(minutes=8), instance="old")

    # A lease left by the pre-Postgres code ("<holder>|<iso expiry>") keeps its expiry, then lapses.
    db.merge(Setting(key="schedule_lease", value=f"web:1:abc|{(now + timedelta(minutes=5)).isoformat()}"))
    db.commit()
    assert not scheduler.hold_lease(db, now + timedelta(minutes=1), instance="new")
    assert scheduler.hold_lease(db, now + timedelta(minutes=6), instance="new")


class FakeContainer:
    def __init__(self):
        self.blobs = {}

    def upload_blob(self, name, data, overwrite=False):
        self.blobs[name] = data.read()


@pytest.mark.skipif(not str(SessionLocal.kw["bind"].url).startswith("sqlite"), reason="SQLite file backups only")
def test_nightly_backup_is_a_working_database(client, auth, db, monkeypatch, tmp_path):
    import gzip
    import sqlite3

    from app.services import backup

    container = FakeContainer()
    monkeypatch.setattr(config, "BACKUP_CONTAINER_URL", "https://example.blob.core.windows.net/db-backups")
    monkeypatch.setattr(backup, "make_container", lambda: container)
    db.execute(SyncRun.__table__.delete().where(SyncRun.kind == "backup"))
    db.commit()

    four_am = datetime.utcnow().replace(hour=4, minute=0, second=0, microsecond=0)
    scheduler.data_tick(db, four_am)
    run = db.scalar(select(SyncRun).where(SyncRun.kind == "backup"))
    assert run.status == "ok" and run.triggered_by == sync.AUTO
    (name, data), = container.blobs.items()
    restored = tmp_path / "restored.db"
    restored.write_bytes(gzip.decompress(data))
    con = sqlite3.connect(restored)
    assert con.execute("pragma integrity_check").fetchone() == ("ok",)
    assert con.execute("select count(*) from users").fetchone()[0] >= 1
    con.close()

    scheduler._attempts.clear()
    scheduler.data_tick(db, four_am + timedelta(hours=2))
    assert len(container.blobs) == 1  # once a day
    r = client.post(f"{API}/admin/backup", headers=auth).json()
    assert r["status"] == "ok" and r["triggered_by"] == "Ivo"
