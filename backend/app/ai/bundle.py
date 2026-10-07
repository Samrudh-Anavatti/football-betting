"""The match bundle Claude reads: the same data as the match page, compacted.

Built once per thread and stored with it, so every analysis can be traced to
exactly what the model saw. Serialised with sorted keys so the same data always
gives the same bytes (prompt caching is a byte-prefix match).
"""
import hashlib
import json
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import Fixture, MatchContext
from ..serialize import iso
from ..services.board import match_board

# Long lists (scorers, exact scores) are cut to the shortest prices.
MAX_LIST_SELECTIONS = 15


def _markets(board: dict) -> list[dict]:
    out = []
    for m in board["markets"]:
        groups = []
        for g in m["groups"]:
            sels = g["selections"][:MAX_LIST_SELECTIONS] if m["layout"] == "list" else g["selections"]
            groups.append({
                **({"line": g["line"]} if g["line"] is not None else {}),
                **({"margin": g["margin"]} if g["margin"] is not None else {}),
                "selections": [
                    {"value": s["value"], "best": s["best"], "at": s["best_bookmaker"],
                     **({"fair_prob": s["prob"]} if s["prob"] is not None else {})}
                    for s in sels
                ],
            })
        entry = {"market_id": m["id"], "market": m["name"], "category": m["category"], "groups": groups}
        if m["layout"] == "list" and len(m["groups"][0]["selections"]) > MAX_LIST_SELECTIONS:
            entry["note"] = f"shortest {MAX_LIST_SELECTIONS} of {len(m['groups'][0]['selections'])} selections"
        out.append(entry)
    return out


def build_bundle(db: Session, fx: Fixture) -> dict:
    ctx = db.get(MatchContext, fx.id)
    load = lambda s: json.loads(s) if s else None  # noqa: E731
    board = match_board(db, fx.id)
    table = load(fx.league.standings_json) or []
    injuries = load(ctx.injuries_json) if ctx else None

    gaps = []
    if not board["markets"]:
        gaps.append("No bookmaker prices pulled")
    if ctx is None:
        gaps.append("No research pulled (form, head-to-head, injuries, team stats)")
    else:
        if not ctx.home_stats_json:
            gaps.append("No season stats per team")
        if not ctx.prediction_json:
            gaps.append("No API-Football prediction")
        if not ctx.lineups_json:
            gaps.append("Line-ups not confirmed yet")
    if not table:
        gaps.append("No league table")

    def team_rows(team_id):
        return [i for i in injuries or [] if i.get("team_id") == team_id]

    return {
        "match": {
            "fixture_id": fx.id,
            "competition": fx.league.name,
            "country": fx.league.country,
            "round": fx.round,
            "kickoff_utc": iso(fx.kickoff),
            "venue": fx.venue,
            "home": fx.home_team.name,
            "away": fx.away_team.name,
        },
        "league_table": [
            {k: r.get(k) for k in ("rank", "team", "played", "points", "gd", "form", "group")} for r in table
        ],
        "recent_form": {
            "home": load(ctx.home_form_json) if ctx else None,
            "away": load(ctx.away_form_json) if ctx else None,
        },
        "head_to_head": load(ctx.h2h_json) if ctx else None,
        "injuries_and_suspensions": {"home": team_rows(fx.home_team_id), "away": team_rows(fx.away_team_id)}
        if injuries is not None else None,
        "season_stats_this_competition": {
            "home": load(ctx.home_stats_json) if ctx else None,
            "away": load(ctx.away_stats_json) if ctx else None,
        },
        "api_football_prediction": load(ctx.prediction_json) if ctx else None,
        "lineups": load(ctx.lineups_json) if ctx else None,
        "research_fetched_at": iso(ctx.fetched_at) if ctx else None,
        "prices": {
            "pulled_at": iso(board["pulled_at"]),
            "bookmakers": board["bookmakers"],
            "note": "best = best price across these bookmakers; fair_prob = margin-free consensus "
                    "probability, only where a bookmaker prices a complete set of outcomes",
            "markets": _markets(board),
        },
        "data_gaps": gaps,
        "bundle_built_at": iso(datetime.utcnow()),
    }


def serialise(bundle: dict) -> tuple[str, str]:
    text = json.dumps(bundle, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return text, hashlib.sha256(text.encode()).hexdigest()


def find_selection(bundle: dict, market_id: int, value: str) -> dict | None:
    """The bundle's entry for a selection: {"value", "best", "at", ...}."""
    for m in bundle.get("prices", {}).get("markets", []):
        if m["market_id"] != market_id:
            continue
        for g in m["groups"]:
            for s in g["selections"]:
                if s["value"] == value:
                    return {**s, "market": m["market"]}
    return None
