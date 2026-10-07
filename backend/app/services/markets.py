"""The full market board: every market API-Football's /odds carries for a match,
for our chosen bookmakers, grouped into categories for the match page.

A "book" is API-Football's shape, kept as-is:
    [{"id": 8, "name": "Bet365", "bets": [{"id": 5, "name": "Goals Over/Under",
                                          "values": [{"value": "Over 2.5", "odd": "1.80"}]}]}]

For each market we work out, per selection, the best price across bookmakers and
a margin-free "fair" price (each bookmaker's implied probabilities normalised to
100%, then averaged). Fair is only computed where a bookmaker prices a complete,
mutually exclusive set of outcomes (overround between 100% and 135%), so it is
skipped for things like anytime-scorer lists, where it would mean nothing.
"""
import re
from collections import defaultdict
from datetime import datetime

from ..models import Fixture, OddsSnapshot

# Markets that also exist in our short codes: odds_snapshots history, closing
# price and the original settlement code all use these.
MATCH_WINNER, GOALS_OU, BTTS = 1, 5, 8
CODE_FOR_MARKET = {MATCH_WINNER: "1X2", GOALS_OU: "OU", BTTS: "BTTS"}
MARKET_FOR_CODE = {v: k for k, v in CODE_FOR_MARKET.items()}
NAME_FOR_CODE = {"1X2": "Match Winner", "OU": "Goals Over/Under", "BTTS": "Both Teams Score"}

# Shown first, in the "Main" tab.
MAIN_MARKETS = [MATCH_WINNER, 12, 2, GOALS_OU, BTTS]  # result, double chance, draw no bet, goals, BTTS

CATEGORIES = [
    ("main", "Main"),
    ("goals", "Goals"),
    ("halves", "Halves"),
    ("scores", "Scores"),
    ("handicaps", "Handicaps"),
    ("corners", "Corners"),
    ("cards", "Cards"),
    ("players", "Players"),
    ("stats", "Match stats"),
    ("specials", "Specials"),
]

_LINE = re.compile(r"^(Over|Under|Home|Away|Draw|Exactly)\s+([+-]?\d+(?:\.\d+)?)$", re.I)


def category(market_id: int, name: str) -> str:
    n = (name or "").lower()
    if market_id in MAIN_MARKETS:
        return "main"
    if any(k in n for k in ("scorer", "player", "goal method", "score or assist", "shots")):
        return "players"
    if "card" in n or "booking" in n:
        return "cards"
    if "corner" in n:
        return "corners"
    if any(k in n for k in ("offside", "foul", "throw", "goal kick")):
        return "stats"
    if any(k in n for k in ("half", "ht/ft", "1st", "2nd", "10 min", "first 10", "rtg_h1")):
        return "halves"
    if any(k in n for k in ("exact score", "correct score", "exact goals", "number of goals", "winning margin")):
        return "scores"
    if "handicap" in n:
        return "handicaps"
    if any(k in n for k in ("goal", "over/under", "total", "both teams", "odd/even", "clean sheet", "win to nil")):
        return "goals"
    return "specials"


def parse_value(value) -> tuple[str, float | None]:
    """'Over 2.5' -> ('Over', 2.5); 'Home -1.25' -> ('Home', -1.25); '2:1' -> ('2:1', None)."""
    v = str(value).strip()
    m = _LINE.match(v)
    if m:
        return m.group(1).capitalize(), float(m.group(2))
    return v, None


def filter_bookmakers(bookmakers: list[dict], ids: list[int]) -> list[dict]:
    keep = [b for b in bookmakers if b.get("id") in ids]
    return sorted(keep, key=lambda b: ids.index(b["id"]))


def _price(odd) -> float | None:
    try:
        p = float(odd)
    except (TypeError, ValueError):
        return None
    return p if p > 1.0 else None


def _fair(group_sels: list[str], books: dict[str, dict[str, float]]) -> tuple[dict[str, float], float | None]:
    """Average margin-free probability per selection, plus the average margin."""
    probs, margins = defaultdict(list), []
    for prices in books.values():
        if set(prices) != set(group_sels) or len(group_sels) < 2:
            continue
        total = sum(1 / p for p in prices.values())
        if not 1.0 < total < 1.35:
            continue
        margins.append(total - 1)
        for sel, p in prices.items():
            probs[sel].append((1 / p) / total)
    fair = {sel: sum(ps) / len(ps) for sel, ps in probs.items()}
    return fair, (sum(margins) / len(margins) if margins else None)


def _main_line(groups: list[dict]) -> float | None:
    """The most balanced line: where the two sides' fair probabilities are closest."""
    best, score = None, None
    for g in groups:
        sels = g["selections"]
        if len(sels) != 2 or any(s["fair"] is None for s in sels):
            continue
        d = abs(1 / sels[0]["fair"] - 1 / sels[1]["fair"])
        if score is None or d < score:
            best, score = g["line"], d
    if best is None and groups:
        best = groups[len(groups) // 2]["line"]
    return best


def build_markets(bookmakers: list[dict]) -> list[dict]:
    """All markets on the board, each with per-line groups of selections.
    A selection's `prices` line up with the bookmakers list (None = not offered)."""
    book_names = [b["name"] for b in bookmakers]
    # (market_id) -> name, ordered selections, and {selection: {bookmaker: price}}
    names, order, prices = {}, defaultdict(list), defaultdict(lambda: defaultdict(dict))
    for bk in bookmakers:
        for bet in bk.get("bets", []):
            mid = bet["id"]
            names.setdefault(mid, bet.get("name") or f"Market {mid}")
            for v in bet.get("values", []):
                p = _price(v.get("odd"))
                if p is None:
                    continue
                val = str(v.get("value")).strip()
                if val not in prices[mid]:
                    order[mid].append(val)
                prices[mid][val][bk["name"]] = p

    markets = []
    for mid, name in names.items():
        sels = order[mid]
        if not sels:
            continue
        parsed = {s: parse_value(s) for s in sels}
        has_lines = all(line is not None for _, line in parsed.values())
        # Group selections that are priced against each other: one group per line,
        # or a single group for everything else.
        groups_raw: dict[float | None, list[str]] = defaultdict(list)
        # Handicaps are written from the home side for both selections:
        # "Away -1.25" is the other half of "Home -1.25" (away gets +1.25).
        for s in sels:
            groups_raw[parsed[s][1] if has_lines else None].append(s)

        groups = []
        for line, gsels in sorted(groups_raw.items(), key=lambda kv: (kv[0] is None, kv[0] or 0)):
            books = defaultdict(dict)
            for s in gsels:
                for book, p in prices[mid][s].items():
                    books[book][s] = p
            fair, margin = _fair(gsels, books)
            selections = []
            for s in gsels:
                by_book = prices[mid][s]
                best_book = max(by_book, key=by_book.get)
                best = by_book[best_book]
                f = round(1 / fair[s], 2) if s in fair else None
                selections.append({
                    "value": s,
                    "side": parsed[s][0],
                    "line": parsed[s][1],
                    "best": best,
                    "best_bookmaker": best_book,
                    "fair": f,
                    "prob": round(fair[s], 4) if s in fair else None,
                    "edge": round(best / f - 1, 4) if f else None,
                    "prices": [by_book.get(b) for b in book_names],
                })
            groups.append({"line": line, "margin": round(margin, 4) if margin is not None else None, "selections": selections})

        many = not has_lines and len(sels) > 8
        if many:  # long lists (scores, players): most likely first
            groups[0]["selections"].sort(key=lambda s: s["best"])
        markets.append({
            "id": mid,
            "name": name,
            "category": category(mid, name),
            "layout": "lines" if has_lines else "list" if many else "outcomes",
            "main_line": _main_line(groups) if has_lines else None,
            "bookmakers": len({b for s in sels for b in prices[mid][s]}),
            "groups": groups,
        })

    cat_rank = {k: i for i, (k, _) in enumerate(CATEGORIES)}
    main_rank = {m: i for i, m in enumerate(MAIN_MARKETS)}
    markets.sort(key=lambda m: (cat_rank[m["category"]], main_rank.get(m["id"], 99), m["id"]))
    return markets


def build_board(bookmakers: list[dict], pulled_at: datetime | None, source: str) -> dict:
    markets = build_markets(bookmakers)
    counts = defaultdict(int)
    for m in markets:
        counts[m["category"]] += 1
    return {
        "source": source,
        "pulled_at": pulled_at,
        "bookmakers": [b["name"] for b in bookmakers],
        "categories": [{"key": k, "label": label, "count": counts[k]} for k, label in CATEGORIES if counts[k]],
        "markets": markets,
    }


# ── Conversions to and from our short codes ──────────────────────────────────


_SEL_TO_VALUE = {
    "1X2": {"home": "Home", "draw": "Draw", "away": "Away"},
    "BTTS": {"yes": "Yes", "no": "No"},
}


def book_from_snapshots(rows: list[OddsSnapshot]) -> list[dict]:
    """Present legacy/Odds API snapshot rows in API-Football's book shape."""
    books: dict[str, dict] = {}
    for r in rows:
        bk = books.setdefault(r.bookmaker_key, {"id": r.bookmaker_key, "name": r.bookmaker, "bets": {}})
        mid = MARKET_FOR_CODE.get(r.market)
        if mid is None:
            continue
        bet = bk["bets"].setdefault(mid, {"id": mid, "name": NAME_FOR_CODE[r.market], "values": []})
        value = f"{r.selection.capitalize()} {r.line:g}" if r.market == "OU" else _SEL_TO_VALUE[r.market].get(r.selection, r.selection)
        bet["values"].append({"value": value, "odd": r.price})
    return [{**b, "bets": list(b["bets"].values())} for b in books.values()]


def to_code(market_id: int | None, value: str) -> tuple[str, str, float | None] | None:
    """API-Football (market, value) -> our (code, selection, line), if it has one."""
    code = CODE_FOR_MARKET.get(market_id)
    if code is None:
        return None
    side, line = parse_value(value)
    if code == "OU":
        return (code, side.lower(), line) if side in ("Over", "Under") and line is not None else None
    sel = side.lower()
    return (code, sel, None) if sel in ({"home", "draw", "away"} if code == "1X2" else {"yes", "no"}) else None


def snapshots_from_book(bookmakers: list[dict], fx: Fixture, pulled_at: datetime) -> list[OddsSnapshot]:
    """Core-market rows for odds_snapshots (price history and the fixture list)."""
    rows = []
    for bk in bookmakers:
        for bet in bk.get("bets", []):
            if bet["id"] not in CODE_FOR_MARKET:
                continue
            for v in bet.get("values", []):
                code = to_code(bet["id"], str(v.get("value")))
                p = _price(v.get("odd"))
                if code is None or p is None:
                    continue
                rows.append(OddsSnapshot(
                    fixture_id=fx.id, pulled_at=pulled_at, bookmaker_key=f"af{bk['id']}", bookmaker=bk["name"],
                    market=code[0], selection=code[1], line=code[2], price=p,
                ))
    return rows


def best_price(bookmakers: list[dict], market_id: int, value: str) -> float | None:
    prices = [
        p for bk in bookmakers for bet in bk.get("bets", []) if bet["id"] == market_id
        for v in bet.get("values", []) if str(v.get("value")).strip() == value and (p := _price(v.get("odd")))
    ]
    return max(prices) if prices else None


def market_probs(markets: list[dict]) -> dict:
    """Margin-free probabilities for the markets the AI is scored on."""
    out = {}
    by_id = {m["id"]: m for m in markets}
    if (m := by_id.get(MATCH_WINNER)) and m["groups"]:
        out["result"] = {s["value"].lower(): s["prob"] for s in m["groups"][0]["selections"] if s["prob"]}
    if (m := by_id.get(GOALS_OU)):
        for g in m["groups"]:
            if g["line"] == 2.5:
                out["over_2_5"] = next((s["prob"] for s in g["selections"] if s["side"] == "Over"), None)
    if (m := by_id.get(BTTS)) and m["groups"]:
        out["btts_yes"] = next((s["prob"] for s in m["groups"][0]["selections"] if s["value"] == "Yes"), None)
    return out
