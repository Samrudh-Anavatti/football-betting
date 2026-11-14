"""Tonight's bundles: the AI's legs built into a few multis for the matches someone is sitting down to watch.

Upcoming matches that have AI legs are grouped into viewing *sessions* (kick-offs within a couple of hours of the
first). A viewer picks a session, ticks the matches they'll watch and a target (about 3.00, 6.00 or 10.00), and
`build` makes up to three bundles from the legs on those matches, each at one bookmaker and each from different
legs, so one leg failing doesn't sink the lot. Flat stakes: the viewer stakes what they like, and every bundle shown
is stored and settled so the record is real. A repeat of the same request (same session, matches and target) gets the
same bundles back rather than new ones.
"""
import hashlib
import math
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Fixture, SessionBundle, SessionBundleLeg, Tip
from ..serialize import fixture_dict, iso, tip_dict
from .ai_staking import pick_bundle
from .stats import current_prices

TARGETS = {"safer": 3.0, "standard": 6.0, "big": 10.0}
HORIZON = timedelta(days=3)  # sessions this far ahead are offered
LEAD = timedelta(minutes=5)  # a match this close to kick-off (or started) is out
SESSION_GAP = timedelta(hours=2, minutes=30)  # a kick-off this long after a session's first starts a new one
MAX_BUNDLES = 3


def _open_legs(db: Session, now: datetime, until: datetime, fixture_ids: list[int] | None = None) -> list[Tip]:
    q = (select(Tip).join(Fixture)
         .where(Tip.source == "ai_leg", Tip.status == "pending", Fixture.status == "NS",
                Fixture.kickoff > now + LEAD, Fixture.kickoff <= until))
    if fixture_ids is not None:
        q = q.where(Tip.fixture_id.in_(fixture_ids))
    return list(db.scalars(q))


def group_sessions(fixtures: list[Fixture]) -> list[list[Fixture]]:
    """Kick-off order; a match starts a new session when it kicks off more than SESSION_GAP after the session's first."""
    groups: list[list[Fixture]] = []
    for fx in sorted(fixtures, key=lambda f: (f.kickoff, f.id)):
        if groups and fx.kickoff - groups[-1][0].kickoff <= SESSION_GAP:
            groups[-1].append(fx)
        else:
            groups.append([fx])
    return groups


def sessions(db: Session, now: datetime | None = None) -> list[dict]:
    """The viewing sessions on offer: each with its matches (those that have legs) and how many legs each has.
    A session needs two matches, since one match's legs can't reach even the lowest target."""
    now = now or datetime.utcnow()
    legs = _open_legs(db, now, now + HORIZON)
    counts: dict[int, int] = {}
    fixtures: dict[int, Fixture] = {}
    for t in legs:
        counts[t.fixture_id] = counts.get(t.fixture_id, 0) + 1
        fixtures[t.fixture_id] = t.fixture
    out = []
    for group in group_sessions(list(fixtures.values())):
        if len(group) < 2:
            continue
        out.append({
            "at": iso(group[0].kickoff), "until": iso(group[-1].kickoff),
            "matches": [{**fixture_dict(fx), "legs": counts[fx.id]} for fx in group],
            "legs": sum(counts[fx.id] for fx in group),
        })
    return out


def request_key(session_at: datetime, fixture_ids: list[int], target: float) -> str:
    raw = f"{session_at.isoformat(timespec='minutes')}|{','.join(map(str, sorted(set(fixture_ids))))}|{target:g}"
    return hashlib.sha1(raw.encode()).hexdigest()


def build(db: Session, session_at: datetime, fixture_ids: list[int], target: float, user_id: int | None = None,
          now: datetime | None = None) -> list[SessionBundle]:
    """The bundles for this request: the ones made before if it was asked before, else up to three new ones from
    the legs on these matches (which must be in the session), likeliest first, each from legs the others don't use.
    Commits. An empty list when the legs can't reach the target."""
    now = now or datetime.utcnow()
    key = request_key(session_at, fixture_ids, target)
    existing = list(db.scalars(select(SessionBundle).where(SessionBundle.key == key).order_by(SessionBundle.position)))
    if existing:
        return existing
    legs = _open_legs(db, now, session_at + SESSION_GAP, fixture_ids)
    legs = [t for t in legs if t.fixture.kickoff >= session_at]
    pool = sorted(((t, current_prices(db, t)) for t in legs), key=lambda x: (-(x[0].ai_probability or 0), x[0].fixture.kickoff))
    made = []
    while pool and len(made) < MAX_BUNDLES:
        found = pick_bundle(pool, target, per_match=2)  # both of a match's legs may go in: the AI picks them not to move together
        if found is None:
            break
        bookmaker, chosen = found
        used = {t.id for t, _ in chosen}
        pool = [x for x in pool if x[0].id not in used]
        made.append(SessionBundle(session_at=session_at, key=key, position=len(made) + 1, target=target,
                                  odds=round(math.prod(p for _, p in chosen), 2), bookmaker=bookmaker, user_id=user_id,
                                  legs=[SessionBundleLeg(tip_id=t.id, odds=p) for t, p in chosen]))
    db.add_all(made)
    db.commit()
    return made


def settle(db: Session) -> int:
    """Settle pending session bundles whose legs have been decided (a lost leg loses it straight away; void legs
    count at 1.00). Profit is in units, at one unit staked."""
    n = 0
    for b in db.scalars(select(SessionBundle).where(SessionBundle.status == "pending")):
        statuses = [leg.tip.status for leg in b.legs]
        if "lost" in statuses:
            b.status, b.profit = "lost", -1.0
        elif "pending" in statuses:
            continue
        elif all(s == "void" for s in statuses):
            b.status, b.profit = "void", 0.0
        else:
            b.status, b.profit = "won", round(math.prod(leg.odds for leg in b.legs if leg.tip.status == "won") - 1, 2)
        b.settled_at = datetime.utcnow()
        n += 1
    return n


def bundle_dict(b: SessionBundle) -> dict:
    return {
        "id": b.id, "position": b.position, "target": b.target, "odds": b.odds, "bookmaker": b.bookmaker,
        "status": b.status, "profit": b.profit, "session_at": iso(b.session_at), "created_at": iso(b.created_at),
        "settled_at": iso(b.settled_at),
        "legs": [{"tip_id": leg.tip_id, "odds": leg.odds, "tip": tip_dict(leg.tip)} for leg in b.legs],
    }


def record(db: Session, limit: int = 12) -> dict:
    """How the bundles have done: totals at one unit each, and the last few sessions with their settled bundles.
    Every bundle ever shown counts once, including ones built for different match selections of the same session."""
    settled = list(db.scalars(select(SessionBundle).where(SessionBundle.status.in_(["won", "lost"]))
                              .order_by(SessionBundle.session_at.desc(), SessionBundle.id)))
    by_session: dict[datetime, list[SessionBundle]] = {}
    for b in settled:
        by_session.setdefault(b.session_at, []).append(b)
    recent = [{"at": iso(at), "won": sum(b.status == "won" for b in rows), "bundles": [bundle_dict(b) for b in rows]}
              for at, rows in list(by_session.items())[:limit]]
    won = sum(b.status == "won" for b in settled)
    return {
        "bundles": len(settled), "won": won, "lost": len(settled) - won,
        "profit_units": round(sum(b.profit or 0 for b in settled), 2),
        "pending": db.scalar(select(func.count()).where(SessionBundle.status == "pending")),
        "sessions": recent,
    }
