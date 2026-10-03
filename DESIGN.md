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
| Bookmaker prices | The Odds API `/sports/{key}/odds` | 500 credits/month | markets × regions per league; 0 if no events |
| Single-match prices | The Odds API `/events/{id}/odds` | (same) | markets × regions |

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
`match_context` (H2H/form/injuries as JSON), `odds_snapshots`.

`odds_snapshots` is **append-only**: every pull adds rows stamped with `pulled_at`,
and "current prices" means the latest pull. Keeping history lets us compute
**closing-line value** (did the pick beat the last pre-kick-off price?), which is
the best single indicator of a tipster with a real edge. It also lets us chart
price movement later.

Our data (never touched by syncs): `users`, `tips`, `bets`.

Bookkeeping: `sync_runs`, `provider_quota`.

### Settlement

When a fixtures sync sees a match finished (`FT`/`AET`/`PEN`), pending tips and bets
on it settle on the 90-minute score. Supported markets are match result, over/under
on whole and half lines (whole lines push = void), and both teams to score.
Postponed/cancelled/abandoned matches void the bet. Quarter lines and anything odd
are settled by hand in Admin → Picks.

### The odds board

For each market the match page shows every bookmaker's latest price and highlights
the best one. It also shows a **fair price**: the average implied probability
across bookmakers with each one's margin removed. **Best vs fair** shows how far
the best available price sits above the consensus, which gives a quick value
signal before Ivo applies his own judgement.

## Security

* Public endpoints are read-only and serve cached data.
* Admin endpoints need a bearer token from `/auth/login`. Accounts come from
  `USERS` + `PASSWORD_<NAME>` app settings and are reconciled on every startup.
* API keys live only in App Service settings. The repo is public and holds no
  secrets.

## Next: LLM

`GET /api/v1/matches/{id}` already returns the full bundle (fixture, odds board
with fair prices, H2H, form, injuries, table, existing picks). The LLM step is:

1. A `POST /admin/matches/{id}/analyse` that serialises that bundle into a prompt
   (Claude, via the Anthropic API) along with Ivo's rules of thumb, and asks for a
   structured suggestion (market, selection, minimum acceptable price, confidence,
   reasoning).
2. Store suggestions alongside tips (`source = llm`) so the LLM gets its **own
   track record** and can be compared with Ivo's.
3. Later: a daily "shortlist" across all priced fixtures, ranked by best-vs-fair
   edge and the LLM's view.
