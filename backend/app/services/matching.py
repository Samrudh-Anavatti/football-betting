"""Link The Odds API events to API-Football fixtures.

The two providers name teams differently ("Bayern München" vs "Bayern Munich",
"Wolves" vs "Wolverhampton Wanderers"), so we match on league + kickoff time
(within a window) + fuzzy team-name similarity.
"""
import re
import unicodedata
from datetime import datetime, timedelta
from difflib import SequenceMatcher

# Tokens that carry no identity ("FC Barcelona" == "Barcelona").
_NOISE = {
    "fc", "cf", "afc", "sc", "ac", "as", "ss", "ssc", "sv", "fk", "sk", "bk", "if", "cd", "ud", "rc", "rcd",
    "club", "de", "the", "calcio", "1", "ogc", "osc", "losc", "stade", "sporting", "cp", "sad", "hotspur",
}

# Known nicknames → canonical form (after normalisation).
_ALIASES = {
    "wolves": "wolverhampton wanderers",
    "spurs": "tottenham",
    "man utd": "manchester united",
    "man united": "manchester united",
    "man city": "manchester city",
    "inter milan": "inter",
    "internazionale": "inter",
    "bayern munich": "bayern munchen",
    "psg": "paris saint germain",
    "atletico madrid": "atletico madrid",
    "athletic bilbao": "athletic",
    "nottingham forest": "nottingham forest",
    "brighton and hove albion": "brighton",
    "west ham united": "west ham",
}

MAX_KICKOFF_DRIFT = timedelta(hours=3)
MIN_SCORE = 0.62


def normalise(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = _ALIASES.get(s, s)
    tokens = [t for t in s.split() if t not in _NOISE]
    s = " ".join(tokens) or s
    return _ALIASES.get(s, s)


def name_similarity(a: str, b: str) -> float:
    na, nb = normalise(a), normalise(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.9
    ratio = SequenceMatcher(None, na, nb).ratio()
    ta, tb = set(na.split()), set(nb.split())
    overlap = len(ta & tb) / max(len(ta | tb), 1)
    return max(ratio, overlap)


def best_fixture_for_event(
    event_home: str, event_away: str, event_kickoff: datetime, candidates: list
) -> tuple[object | None, float]:
    """candidates: fixtures with .kickoff, .home_team.name, .away_team.name.
    Returns (fixture, score) or (None, best_score)."""
    best, best_score = None, 0.0
    for fx in candidates:
        if abs(fx.kickoff - event_kickoff) > MAX_KICKOFF_DRIFT:
            continue
        score = (name_similarity(event_home, fx.home_team.name) + name_similarity(event_away, fx.away_team.name)) / 2
        if score > best_score:
            best, best_score = fx, score
    return (best, best_score) if best_score >= MIN_SCORE else (None, best_score)
