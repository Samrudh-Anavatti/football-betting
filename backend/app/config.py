"""Runtime configuration (env vars) + the league catalogue.

Everything tunable lives in App Service settings / backend/.env, so keys and
quota pacing can change without a redeploy (just a restart).
"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "").strip()
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "").strip()

FOOTBALL_SEASON = int(os.getenv("FOOTBALL_SEASON", "2026"))
# Free API-Football plan: 10 requests/minute. Calls are spaced by this many seconds.
API_FOOTBALL_MIN_INTERVAL = float(os.getenv("API_FOOTBALL_MIN_INTERVAL", "6.5"))

JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-secret")
TOKEN_DAYS = int(os.getenv("TOKEN_DAYS", "14"))

# The Odds API (backup price source: match result and totals only).
ODDS_REGIONS = ["uk", "eu"]
ODDS_MARKETS = ["h2h", "totals"]

# Main price source: API-Football's /odds (every market it carries), kept for
# these bookmakers only. Ids from /odds/bookmakers. Default: Bet365, William
# Hill, Betfair, BetVictor, Pinnacle (the sharp reference for fair prices).
ODDS_BOOKMAKERS = [int(x) for x in os.getenv("ODDS_BOOKMAKERS", "8,7,3,36,4").split(",") if x.strip()]

# ── AI analysis (GPT-5.6 Luna on Microsoft Foundry) ──
# FOUNDRY_RESOURCE is the resource name (foundry-football-sa), not the URL.
FOUNDRY_RESOURCE = os.getenv("FOUNDRY_RESOURCE", "").strip()
FOUNDRY_API_KEY = os.getenv("FOUNDRY_API_KEY", "").strip()
DEFAULT_AI_MODEL = "gpt-5.6-luna"
AI_MODEL = os.getenv("AI_MODEL", DEFAULT_AI_MODEL)  # the Foundry deployment name
AI_EFFORT = os.getenv("AI_EFFORT", "high")  # reasoning effort: low | medium | high
AI_MONTHLY_BUDGET_USD = float(os.getenv("AI_MONTHLY_BUDGET_USD", "20"))
# USD per million tokens (Azure Global Standard, short context): input, output, cached input.
AI_PRICES = {
    "gpt-5.6-luna": (0.20, 1.20, 0.02),
    "gpt-5.6-terra": (2.00, 12.00, 0.20),
}


@dataclass(frozen=True)
class LeagueDef:
    id: int  # API-Football league id (our primary key)
    name: str
    country: str
    odds_key: str  # The Odds API sport key
    flag: str  # emoji flag, used as a lightweight badge


# Ivo's leagues: top flight of ten countries plus the two big UEFA comps.
LEAGUES: list[LeagueDef] = [
    LeagueDef(39, "Premier League", "England", "soccer_epl", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"),
    LeagueDef(140, "La Liga", "Spain", "soccer_spain_la_liga", "🇪🇸"),
    LeagueDef(135, "Serie A", "Italy", "soccer_italy_serie_a", "🇮🇹"),
    LeagueDef(78, "Bundesliga", "Germany", "soccer_germany_bundesliga", "🇩🇪"),
    LeagueDef(61, "Ligue 1", "France", "soccer_france_ligue_one", "🇫🇷"),
    LeagueDef(94, "Primeira Liga", "Portugal", "soccer_portugal_primeira_liga", "🇵🇹"),
    LeagueDef(88, "Eredivisie", "Netherlands", "soccer_netherlands_eredivisie", "🇳🇱"),
    LeagueDef(203, "Süper Lig", "Turkey", "soccer_turkey_super_league", "🇹🇷"),
    LeagueDef(144, "Jupiler Pro League", "Belgium", "soccer_belgium_first_div", "🇧🇪"),
    LeagueDef(253, "MLS", "USA", "soccer_usa_mls", "🇺🇸"),
    LeagueDef(2, "Champions League", "Europe", "soccer_uefa_champs_league", "🇪🇺"),
    LeagueDef(3, "Europa League", "Europe", "soccer_uefa_europa_league", "🇪🇺"),
]

LEAGUES_BY_ID = {lg.id: lg for lg in LEAGUES}
