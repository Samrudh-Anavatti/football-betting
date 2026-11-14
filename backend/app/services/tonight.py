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


SURE = "ai_leg"  # the AI's bundle legs: 1.15–1.60, 70%+ likely
LONGER = "ai"  # its suggested bets: 1.50–3.00, used only when the sure legs can't reach the target
STRETCH_MAX_LEGS = 10  # a Big night may run to ten legs when it has to


def _open_legs(db: Session, now: datetime, until: datetime, fixture_ids: list[int] | None = None,
               sources: tuple[str, ...] = (SURE,)) -> list[Tip]:
    q = (select(Tip).join(Fixture)
         .where(Tip.source.in_(sources), Tip.status == "pending", Tip.ai_probability.is_not(None), Fixture.status == "NS",
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
    Each bundle is tried from the surest legs first; when those can't reach the target (a thin night), the AI's
    suggested bets join the pool as longer shots and the bundle may run to more legs (`stretch`). Commits. An empty
    list when even that can't reach the target."""
    now = now or datetime.utcnow()
    key = request_key(session_at, fixture_ids, target)
    existing = list(db.scalars(select(SessionBundle).where(SessionBundle.key == key).order_by(SessionBundle.position)))
    if existing:
        return existing
    tips = [t for t in _open_legs(db, now, session_at + SESSION_GAP, fixture_ids, (SURE, LONGER)) if t.fixture.kickoff >= session_at]
    # A suggested bet that duplicates a sure leg's selection is the same bet: keep the leg.
    seen: set[tuple] = set()
    pool = []
    for t in sorted(tips, key=lambda t: (t.source != SURE, -(t.ai_probability or 0), t.fixture.kickoff)):
        sel = (t.fixture_id, t.market, t.selection, t.line)
        if sel not in seen:
            seen.add(sel)
            pool.append((t, current_prices(db, t)))
    made = []
    while pool and len(made) < MAX_BUNDLES:
        # Both of a match's legs may go in: the AI picks them not to move together.
        found, stretch = pick_bundle([x for x in pool if x[0].source == SURE], target, per_match=2), False
        if found is None:
            found, stretch = pick_bundle(pool, target, per_match=3, max_legs=STRETCH_MAX_LEGS), True
        if found is None:
            break
        bookmaker, chosen = found
        used = {t.id for t, _ in chosen}
        pool = [x for x in pool if x[0].id not in used]
        made.append(SessionBundle(session_at=session_at, key=key, position=len(made) + 1, target=target, stretch=stretch,
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
        "status": b.status, "profit": b.profit, "stretch": bool(b.stretch), "session_at": iso(b.session_at),
        "created_at": iso(b.created_at),
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
    by_target = {}
    for name, t in TARGETS.items():
        rows = [b for b in settled if b.target == t]
        by_target[name] = {"target": t, "bundles": len(rows), "won": sum(b.status == "won" for b in rows),
                           "profit_units": round(sum(b.profit or 0 for b in rows), 2)}
    return {
        "bundles": len(settled), "won": won, "lost": len(settled) - won,
        "profit_units": round(sum(b.profit or 0 for b in settled), 2),
        "pending": db.scalar(select(func.count()).where(SessionBundle.status == "pending")),
        "by_target": by_target,
        "legs": leg_record(db),
        "sessions": recent,
    }


def leg_record(db: Session) -> dict:
    """The legs that have appeared in tonight's bundles, each counted once however many bundles it was in: how often
    the surest legs and the longer shots landed, against what their prices implied. This is the number that matters;
    bundles are just combinations of it."""
    out = {}
    for name, source in (("sure", SURE), ("longer", LONGER)):
        tips = list(db.scalars(select(Tip).join(SessionBundleLeg, SessionBundleLeg.tip_id == Tip.id)
                               .where(Tip.source == source, Tip.status.in_(["won", "lost"])).distinct()))
        n = len(tips)
        won = sum(t.status == "won" for t in tips)
        out[name] = {"settled": n, "won": won, "hit_rate": round(won / n, 4) if n else None,
                     "implied_rate": round(sum(1 / t.odds for t in tips) / n, 4) if n else None}
    return out
