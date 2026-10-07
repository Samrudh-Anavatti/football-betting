# Design

## Goals

1. Give Ivo one place to research a match: prices across bookmakers, form,
   head-to-head, injuries, league position.
2. Publish picks with a **verifiable track record**: timestamped, locked at
   kick-off, settled automatically from the final score, never deleted once the
   match has started. That record is the thing that can be monetised later.
3. Track virtual bankrolls for Sam and Ivo.
4. Build the per-match "bundle" so an LLM can later read the same context Ivo does
   (see *Next: LLM* below).

## Data flow

```
 Admin buttons ──► SyncRun (background thread) ──► provider client ──► SQLite cache
                                                        │
                                       quota headers ───┘──► ProviderQuota
 Public site ◄── FastAPI read endpoints ◄── SQLite cache (never calls providers)
```

* **Nothing calls a provider automatically.** Every request is spent from a
  button: Admin → Data (whole leagues) or a match page (one match). This keeps the
  free tiers usable and makes cost visible.
* Each button press is a **SyncRun** row: who, what, progress, requests/credits
  spent, per-league outcome and errors. The admin panel polls it for a live
  progress bar and keeps it as history.
* **Quota** is read from response headers on every call (`x-ratelimit-requests-*`
  for API-Football, `x-requests-*` for The Odds API) and can be refreshed for
  free (`/status` and `/sports` don't cost anything).
* API-Football's free plan allows 10 requests/minute, so calls are spaced by
  `API_FOOTBALL_MIN_INTERVAL` seconds (6.5 by default). A 12-league sync takes
  about 3 minutes, which is why syncs run in the background.

## Providers

| Need | Provider | Free tier | Call cost |
|---|---|---|---|
| Fixtures + results + tables | API-Football `/fixtures?league&season`, `/standings` | 100 req/day, 10/min | 1 per league (+1 for the table) |
| H2H, last 5, injuries | API-Football `/fixtures/headtohead`, `/fixtures?team&season`, `/injuries` | (same) | 4 per match (+2 early in a season) |
| Bookmaker prices, every market | API-Football `/odds?league&season` (paged 10 matches) / `/odds?fixture` | Pro only | 1 per 10 matches / 1 per match |
| Prediction, team stats, line-ups | API-Football `/predictions`, `/teams/statistics`, `/fixtures/lineups` | Pro | 1 each (stats: 1 per team) |
| Backup prices (result, totals) | The Odds API `/sports/{key}/odds` | 500 credits/month | markets × regions per league; 0 if no events |
| AI analysis | GPT-5.6 Luna on Microsoft Foundry (Responses API) | pay per token | ~$0.01 per match, ~$0.001 per follow-up |

Bookmakers don't offer public odds APIs. The Odds API aggregates them through
licensed feeds, so we get the prices without scraping.

**Known risk:** API-Football's free plan has historically limited which *seasons*
are available. If the current season is refused, the admin panel shows the
provider's exact error on the run and on the league row. The fix is the $19/mo
Pro plan; nothing in the code changes.

### Matching odds to fixtures

The two providers name teams differently ("Wolves" / "Wolverhampton Wanderers",
"Bayern München" / "Bayern Munich"). `services/matching.py` matches each odds event
to a fixture in the same league with a kickoff within 3 hours and the best fuzzy
name score (accent stripping, noise tokens like FC/AC, alias table). Once matched,
the event id is stored on the fixture so future pulls link directly. Events that
don't match are listed in the run details. Add an alias when that happens.

## Data model

Provider cache (overwritten by syncs): `leagues`, `teams`, `fixtures`,
`match_context` (H2H/form/injuries/prediction/stats/line-ups as JSON), `market_books` (latest full book per
match, frozen at kick-off), `odds_snapshots`.

`odds_snapshots` is **append-only**: every pull adds rows stamped with `pulled_at`,
and "current prices" means the latest pull. Keeping history lets us compute
**closing-line value** (did the pick beat the last pre-kick-off price?), which is
the best single indicator of a tipster with a real edge. It also lets us chart
price movement later.

Our data (never touched by syncs): `users`, `tips` (Ivo's and the AI's, by `source`), `bets`,
`ai_threads`, `ai_messages`, `ai_predictions`.

Bookkeeping: `sync_runs`, `provider_quota`.

### Settlement

When a fixtures sync sees a match finished (`FT`/`AET`/`PEN`), pending tips and bets
on it settle on the 90-minute score. Supported markets are match result, over/under
on whole and half lines (whole lines push = void), and both teams to score.
Postponed/cancelled/abandoned matches void the bet. Quarter lines and anything odd
are settled by hand in Admin → Picks.

### The market board

Every market our five bookmakers price, in tabs (main, goals, halves, scores, handicaps, corners, cards, players,
match stats, specials) with a search box. Each selection shows the best price (click it to pick), the **fair
price** (each bookmaker's implied probabilities normalised to remove its margin, then averaged) and **best vs
fair**. Fair is only computed where a bookmaker prices a complete, mutually exclusive set of outcomes (overround
100–135%), so it's blank for things like anytime-scorer lists. Over/under and handicap markets show a ladder
around the most balanced line. `services/markets.py` builds it.

## Security

* Public endpoints are read-only and serve cached data.
* Admin endpoints need a bearer token from `/auth/login`. Accounts come from
  `USERS` + `PASSWORD_<NAME>` app settings and are reconciled on every startup.
* API keys live only in App Service settings. The repo is public and holds no
  secrets.

## AI analysis

The AI (GPT-5.6 Luna) reads the same match bundle Ivo sees and records probabilities and value bets through a
strict function, then answers follow-up questions in the same conversation. Suggestions stay private and are tracked as `source='ai'`
tips, so the AI earns its own record against Ivo and the market. Details, costs and setup:
[HANDOFF.md → AI analysis](HANDOFF.md#ai-analysis-built-2026-10-07).
