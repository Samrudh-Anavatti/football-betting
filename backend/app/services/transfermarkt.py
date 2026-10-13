"""Links from a team to its Transfermarkt page (squad and market values).

No scraping: app/data/transfermarkt.json maps our (API-Football) team ids to
Transfermarkt club ids, built once on 2026-10-13 from the CC0 transfermarkt-datasets
clubs table for the nine European top flights and checked by hand. Club ids never
change. Any other team links to Transfermarkt's search for its name. To add a
team: find its page on transfermarkt.com (…/<slug>/startseite/verein/<id>) and add
"<team id>": "<slug>/<id>".
"""
import json
from pathlib import Path
from urllib.parse import quote

BASE = "https://www.transfermarkt.com"
_CLUBS: dict[str, str] = json.loads((Path(__file__).parent.parent / "data" / "transfermarkt.json").read_text("utf-8"))


def team_url(team_id: int, name: str) -> str:
    ref = _CLUBS.get(str(team_id))
    if ref:
        slug, club_id = ref.split("/")
        return f"{BASE}/{slug}/startseite/verein/{club_id}"
    return f"{BASE}/schnellsuche/ergebnis/schnellsuche?query={quote(name)}"
