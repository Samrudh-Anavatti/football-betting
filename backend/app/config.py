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

# Background refresh schedule (services/scheduler.py). "off" stops the threads
# entirely; the on/off switch and credit reserve in Admin → Data are stored in the DB.
SCHEDULER = os.getenv("SCHEDULER", "on").strip().lower()
SCHEDULE_RESERVE = int(os.getenv("SCHEDULE_RESERVE", "2000"))

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
# Scheduled analyses stop at this share of the budget, so the rest stays free for the Analyse button.
AI_AUTO_BUDGET_SHARE = float(os.getenv("AI_AUTO_BUDGET_SHARE", "0.85"))
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
    odds_key: str  # The Odds API sport key ("" = The Odds API doesn't cover it)
    flag: str  # emoji flag, used as a lightweight badge
    # Supplementary leagues: fixtures, results and prices only. Not on the home page;
    # research, line-ups and AI analysis only from the match page's buttons.
    supplementary: bool = False


# Main leagues: top flight of ten countries plus the three UEFA club competitions.
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
    LeagueDef(848, "Conference League", "Europe", "soccer_uefa_europa_conference_league", "🇪🇺"),
] + [
    LeagueDef(i, name, country, key, flag, supplementary=True) for i, name, country, key, flag in [
        # Second and third tiers of the ten countries above (Spain's and Italy's third tiers are regional groups).
        (40, "Championship", "England", "soccer_efl_champ", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"),
        (41, "League One", "England", "soccer_england_league1", "🏴󠁧󠁢󠁥󠁮󠁧󠁿"),
        (141, "Segunda División", "Spain", "soccer_spain_segunda_division", "🇪🇸"),
        (435, "Primera RFEF Group 1", "Spain", "", "🇪🇸"),
        (436, "Primera RFEF Group 2", "Spain", "", "🇪🇸"),
        (136, "Serie B", "Italy", "soccer_italy_serie_b", "🇮🇹"),
        (138, "Serie C Girone A", "Italy", "", "🇮🇹"),
        (942, "Serie C Girone B", "Italy", "", "🇮🇹"),
        (943, "Serie C Girone C", "Italy", "", "🇮🇹"),
        (79, "2. Bundesliga", "Germany", "soccer_germany_bundesliga2", "🇩🇪"),
        (80, "3. Liga", "Germany", "soccer_germany_liga3", "🇩🇪"),
        (62, "Ligue 2", "France", "soccer_france_ligue_two", "🇫🇷"),
        (63, "Ligue 3", "France", "", "🇫🇷"),
        (95, "Liga Portugal 2", "Portugal", "", "🇵🇹"),
        (865, "Liga 3", "Portugal", "", "🇵🇹"),
        (89, "Eerste Divisie", "Netherlands", "", "🇳🇱"),
        (492, "Tweede Divisie", "Netherlands", "", "🇳🇱"),
        (204, "1. Lig", "Turkey", "", "🇹🇷"),
        (205, "2. Lig", "Turkey", "", "🇹🇷"),
        (145, "Challenger Pro League", "Belgium", "", "🇧🇪"),
        (487, "First Amateur Division", "Belgium", "", "🇧🇪"),
        (255, "USL Championship", "USA", "", "🇺🇸"),
        (489, "USL League One", "USA", "", "🇺🇸"),
        # South America and Scotland.
        (71, "Brasileirão Série A", "Brazil", "soccer_brazil_campeonato", "🇧🇷"),
        (72, "Brasileirão Série B", "Brazil", "soccer_brazil_serie_b", "🇧🇷"),
        (128, "Liga Profesional", "Argentina", "soccer_argentina_primera_division", "🇦🇷"),
        (129, "Primera Nacional", "Argentina", "", "🇦🇷"),
        (179, "Scottish Premiership", "Scotland", "soccer_spl", "🏴󠁧󠁢󠁳󠁣󠁴󠁿"),
    ]
]

LEAGUES_BY_ID = {lg.id: lg for lg in LEAGUES}
