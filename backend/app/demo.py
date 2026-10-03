"""Local-only demo data so the UI can be explored without API keys.

    python -m app.demo

Runs fake provider payloads through the real ingestion code (fixtures, odds,
match research), then adds a tip and a bet. Never run this against production.
"""
import json
import random
from datetime import datetime, timedelta

from sqlalchemy import select

from .database import Base, SessionLocal, engine
from .models import Fixture, League, MatchContext, Tip, User
from .seed import sync_users
from .services.settlement import settle_fixture
from .services.sync import ensure_leagues, ingest_odds_events, upsert_fixture

TEAMS = {
    39: ["Arsenal", "Chelsea", "Liverpool", "Manchester City", "Newcastle", "Aston Villa", "Brighton", "Tottenham"],
    140: ["Barcelona", "Real Madrid", "Atletico Madrid", "Villarreal", "Real Sociedad", "Sevilla"],
    135: ["Inter", "Napoli", "AC Milan", "Juventus", "Atalanta", "Roma"],
    78: ["Bayern München", "Borussia Dortmund", "Bayer Leverkusen", "RB Leipzig"],
}
BOOKS = [("williamhill", "William Hill"), ("skybet", "Sky Bet"), ("paddypower", "Paddy Power"), ("betfair_sb_uk", "Betfair Sportsbook")]


def af_item(fid, lid, home, away, kickoff, status="NS", hg=None, ag=None):
    return {
        "fixture": {"id": fid, "date": kickoff.isoformat() + "+00:00", "venue": {"name": f"{home[1]} Stadium"},
                    "status": {"short": status, "long": "Match Finished" if status == "FT" else "Not Started"}},
        "league": {"id": lid, "season": 2026, "round": "Regular Season - 7", "name": ""},
        "teams": {"home": {"id": home[0], "name": home[1], "logo": None}, "away": {"id": away[0], "name": away[1], "logo": None}},
        "goals": {"home": hg, "away": ag}, "score": {"fulltime": {"home": hg, "away": ag}},
    }


def main():
    rnd = random.Random(7)
    Base.metadata.create_all(bind=engine)
    sync_users()
    db = SessionLocal()
    ensure_leagues(db)
    now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    fid, tid = 9000, 9000
    team_ids = {}
    for lid, names in TEAMS.items():
        for n in names:
            team_ids[n] = tid = tid + 1
        lg = db.get(League, lid)
        pairs = list(zip(names[0::2], names[1::2]))
        events = []
        for i, (h, a) in enumerate(pairs):
            ko = now + timedelta(days=i % 3, hours=15 + i)
            fid += 1
            upsert_fixture(db, af_item(fid, lid, (team_ids[h], h), (team_ids[a], a), ko))
            # a played match from 3 days ago (the reverse fixture)
            fid += 1
            upsert_fixture(db, af_item(fid, lid, (team_ids[a], a), (team_ids[h], h), now - timedelta(days=1 + i % 3), "FT", rnd.randint(0, 3), rnd.randint(0, 3)))
            p = [rnd.uniform(1.6, 3.8), rnd.uniform(3.2, 4.2), rnd.uniform(2.0, 5.0)]
            events.append({
                "id": f"demo{fid}", "commence_time": ko.isoformat() + "Z", "home_team": h, "away_team": a,
                "bookmakers": [{"key": k, "title": t, "last_update": now.isoformat() + "Z", "markets": [
                    {"key": "h2h", "outcomes": [{"name": h, "price": round(p[0] * rnd.uniform(0.95, 1.04), 2)},
                                                {"name": "Draw", "price": round(p[1] * rnd.uniform(0.95, 1.04), 2)},
                                                {"name": a, "price": round(p[2] * rnd.uniform(0.95, 1.04), 2)}]},
                    {"key": "totals", "outcomes": [{"name": "Over", "price": round(rnd.uniform(1.7, 2.0), 2), "point": 2.5},
                                                   {"name": "Under", "price": round(rnd.uniform(1.8, 2.1), 2), "point": 2.5}]},
                ]} for k, t in BOOKS],
            })
        db.flush()
        lg.fixtures_synced_at = now - timedelta(days=2)
        lg.standings_synced_at = now - timedelta(days=2)
        lg.standings_json = json.dumps([{"rank": i + 1, "team_id": team_ids[n], "team": n, "points": 20 - 2 * i,
                                         "played": 7, "gd": 9 - 3 * i} for i, n in enumerate(names)])
        ingest_odds_events(db, lg, events, now - timedelta(hours=3))
        lg.odds_synced_at = now - timedelta(hours=3)
    db.commit()

    fx = db.scalar(select(Fixture).where(Fixture.status == "NS").order_by(Fixture.kickoff))
    form = lambda tid_: [{"id": i, "date": (now - timedelta(days=7 * (i + 1))).isoformat() + "+00:00", "league": "", "home": "Them" if i % 2 else "Us",  # noqa: E731
                          "away": "Us" if i % 2 else "Them", "home_id": 0, "away_id": 0, "hg": 1, "ag": 1, "status": "FT",
                          "venue": "A" if i % 2 else "H", "gf": g, "ga": c, "result": "W" if g > c else "L" if g < c else "D"}
                         for i, (g, c) in enumerate([(2, 0), (1, 1), (3, 2), (0, 1), (2, 1)])]
    db.merge(MatchContext(
        fixture_id=fx.id, fetched_at=now - timedelta(hours=5),
        h2h_json=json.dumps([{"id": 1, "date": "2026-03-01T15:00:00+00:00", "league": "", "home": fx.home_team.name,
                              "away": fx.away_team.name, "home_id": 0, "away_id": 0, "hg": 2, "ag": 2, "status": "FT"}]),
        home_form_json=json.dumps(form(1)), away_form_json=json.dumps(form(2)[::-1]),
        injuries_json=json.dumps([{"player": "B. Saka", "team_id": fx.home_team_id, "type": "Missing Fixture", "reason": "Hamstring"}]),
    ))
    ivo = db.scalar(select(User).where(User.username == "ivo"))
    if not db.scalar(select(Tip)):
        db.add(Tip(fixture_id=fx.id, author_id=ivo.id, market="OU", selection="over", line=2.5, odds=1.95,
                   bookmaker="Sky Bet", stake_units=2, confidence=4,
                   reasoning="Both sides have scored in four of their last five and the away defence is missing its first-choice centre-back."))
        played = db.scalar(select(Fixture).where(Fixture.status == "FT"))
        db.add(Tip(fixture_id=played.id, author_id=ivo.id, market="1X2", selection="home", odds=2.1, bookmaker="William Hill",
                   stake_units=1, confidence=3, reasoning="Home side unbeaten in six.", created_at=played.kickoff - timedelta(days=1)))
        db.flush()
        settle_fixture(db, played)
    db.commit()
    print("Demo data loaded.")


if __name__ == "__main__":
    main()
