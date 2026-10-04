# Handoff: operations notes

> **No secrets in here** (the repo is public). Passwords and API keys live only in
> Azure App Service settings.

_Last updated: 2026-10-04 (API-Football Pro live, first full sync done, AI plan written; **next session: build the AI analysis, see the last section**)._

## Live resources

| Thing | Value |
|---|---|
| Frontend | https://samrudh-anavatti.github.io/football-betting/ (GitHub Pages, deploys on push to `main`) |
| Backend | https://football-betting-api-sa.azurewebsites.net (API base `/api/v1`, docs at `/docs`) |
| Resource group | `rg-football-betting` (UK South), **separate from PongPoints** |
| App Service plan | `plan-football-betting`, Linux **B1**, Always On |
| Web app | `football-betting-api-sa`, Python 3.11, startup `bash startup.sh` |
| Database | SQLite at `/home/data/football.db` (persists across deploys) |
| Plans | API-Football **Pro** ($19/mo, 7,500 req/day, upgraded 2026-10-03 for a one-month trial). The Odds API **free** (500 credits/month). |
| Repo | https://github.com/Samrudh-Anavatti/football-betting |

### Why its own B1 (and not PongPoints' plan)

PongPoints (`rg-pongpoints` / `plan-pongpoints`, West Central US) is live and in
use. Sharing its plan would share CPU and memory, so a 3-minute sync or a big
odds pull could slow the club site down, and unpicking them later would mean a
migration. This app has its **own resource group and plan**, so nothing here can
affect PongPoints and either can be resized or deleted on its own. Cost: B1 is
about £10/month. To pause spending, scale to F1:
`az appservice plan update -g rg-football-betting -n plan-football-betting --sku F1`.
F1 has no Always On and a daily CPU cap, so syncs may be cut short.

## Config (App Service → Environment variables)

| Var | Default | Purpose |
|---|---|---|
| `API_FOOTBALL_KEY` | — | API-Football key. Missing = Data tab shows "No API key". |
| `ODDS_API_KEY` | — | The Odds API key. |
| `FOOTBALL_SEASON` | 2026 | Season passed to API-Football (2026 = 2026/27 in Europe, MLS 2026). Bump each summer. |
| `API_FOOTBALL_MIN_INTERVAL` | 6.5 (code default) | Seconds between API-Football calls. **Production: 0.25** (Pro allows 300/min). Does not adjust itself; if we drop back to Free, set it to 6.5. |
| `USERS` | sam,ivo | Accounts. Each needs `PASSWORD_<NAME>`. |
| `PASSWORD_SAM` / `PASSWORD_IVO` | — | Login passwords, reconciled on startup. Rotate = change + restart. |
| `JWT_SECRET` | — | Signs login tokens. Changing it signs everyone out. |
| `CORS_ORIGINS` | — | `https://samrudh-anavatti.github.io,http://localhost:5173` |
| `DATA_DIR` | /home/data | Where SQLite lives. |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | true | Azure pip-installs requirements on deploy. |

GitHub Actions (Settings → Secrets and variables → Actions):
`AZURE_WEBAPP_NAME` (variable), `AZURE_WEBAPP_PUBLISH_PROFILE` (secret),
`VITE_API_URL` (variable, `https://football-betting-api-sa.azurewebsites.net/api/v1`).

**Keep uvicorn to a single worker.** Syncs run in background threads inside the
web process, and SQLite prefers one writer.

## Moving the backend (new plan, region or host)

All state is in one file, `/home/data/football.db`. Everything else is code plus
the settings above.

1. Create the new web app (Python 3.11, startup `bash startup.sh`, same settings).
2. Copy the DB: Kudu (`https://<app>.scm.azurewebsites.net/DebugConsole`) →
   download `/home/data/football.db`, then upload it to the new app's `/home/data/`.
   Losing it only loses picks/bets/history; the provider cache can be re-synced.
3. Point GitHub: update `AZURE_WEBAPP_NAME`, the publish-profile secret and
   `VITE_API_URL`, then re-run both workflows.
4. Add the new frontend origin to `CORS_ORIGINS` if the domain changes.

Moving to Postgres later: set `DATABASE_URL`. The models are plain SQLAlchemy;
only `database.py`'s SQLite pragmas are SQLite-specific.

## Verified against the live APIs (2026-10-03)

* **API-Football free plan only serves seasons 2022–2024.** A 2026 fixtures call
  returns `{"plan": "Free plans do not have access to this season, try from 2022 to 2024."}`.
  The current season needs Pro ($19/mo, 7,500 req/day). `/status` is free and
  reports `requests.current` / `limit_day`. Every response also carries
  `x-ratelimit-requests-remaining` (daily) and `x-ratelimit-remaining` (per minute, 10).
* **The Odds API has no separate usage endpoint in its v4 docs.** Usage comes back
  in `x-requests-remaining` / `-used` / `-last` headers on every call. `/v4/sports`
  and `/v4/sports/{sport}/events` cost 0, so "Check balance" uses `/sports`.
  `/odds` costs markets × regions and is free when no events come back.
* All 12 Odds API sport keys in `config.py` exist and are active.

## State after the first full sync (2026-10-03)

* Fixtures + tables for all 12 leagues: 24 requests, 3,944 fixtures, ran 151 s at the old 6.5 s pacing (about 6 s at 0.25 s).
* Prices for all 12 leagues (match result + total goals, UK books): 24 credits, 182 matches priced.
  Two events didn't match because The Odds API says "Sporting Lisbon" and API-Football says
  "Sporting CP". Fixed with an alias on 2026-10-04.
* Balances after that: API-Football 7,468 / 7,500 today, The Odds API 476 / 500 this month.

## Gotchas

* After changing App Service settings, **restart the app** (`az webapp restart -g rg-football-betting -n football-betting-api-sa`).
  The automatic restart can lag, and the app reads settings at startup.

* API-Football returns HTTP 200 with an `errors` object for problems (bad key,
  season not on plan, rate limit). The client turns these into errors shown in
  the admin panel, so a sync never fails silently.
* Odds API team names differ from API-Football's. Unmatched events are listed in
  the sync history. Add an alias in `backend/app/services/matching.py`.
* Odds snapshots are append-only and will grow by roughly 50–100k rows/month at
  daily pulls of all leagues. That's fine for SQLite; prune old pulls if it ever
  matters.
* Locally, `python -m app.demo` loads fake data. Never run it against production.

## Next steps

* [x] Both API keys added as app settings; balances show in Admin → Data.
* [x] API-Football Pro for a one-month trial (from 2026-10-03). **Review with Ivo around 2026-11-03**: keep Pro only if he uses the Pro-only data (injuries, line-ups, team stats, extra markets), otherwise drop to football-data.org + our own stored history.
* [ ] **AI match analysis, the next session's work** (see "AI predictions: plan" below).
* [ ] Move from SQLite to a database we can browse and monitor (see below).
* [ ] Price-movement chart from odds history; closing-line value per pick.

## Future: a database we can browse

Today the data is a **SQLite file on App Service's persistent disk**
(`/home/data/football.db`). It's on disk, not in memory, so it survives restarts and
deploys, but the only way to look at it is to download it (Kudu → `/home/data`)
and open it in a tool like DB Browser for SQLite.

Plan: move to **Azure Database for PostgreSQL Flexible Server**, Burstable B1ms
(about £10–13/month), in `rg-football-betting`.
* Browse and query it from the portal, VS Code (PostgreSQL extension), pgAdmin or
  DBeaver. Azure Monitor gives CPU/storage/connection metrics and slow-query insights.
* Code change is small: set `DATABASE_URL=postgresql+psycopg://…`, add `psycopg[binary]`,
  and drop the SQLite-only pragmas. Add Alembic for migrations at the same time.
* One-off copy of existing picks/bets from SQLite. The provider cache can just be re-synced.
* A cheaper alternative is the Azure SQL Database free offer (£0, serverless,
  auto-pause), at the cost of ODBC driver setup and a slower first query after a pause.

## Running costs (estimate, Oct 2026)

| Item | £/month |
|---|---|
| App Service B1 Linux, UK South | 9.93 (Azure retail price £0.0136/hr) |
| API-Football Pro ($19) | ~14–15 |
| The Odds API (free) | 0 |
| Claude API for AI analysis (see below) | ~5–12 at a few matches a day |
| Postgres Flexible B1ms (future) | ~10–13 |

Today that's about £25/month, or about £35 once AI analysis is running.

## AI predictions: plan (next session)

**Goal.** For any upcoming match, Claude reads exactly what Ivo sees (the match
bundle) and returns probabilities and value bets in a fixed structure. Those
suggestions get a **track record of their own**, so after a few weeks we can see
whether the AI beats the market, Ivo, or neither. This is meant to be the main
value of the app.

### Ground rules
* **Suggestions are never published automatically.** They're private to Sam and Ivo. A
  suggestion becomes a public pick only when Ivo clicks it and publishes it through the
  existing pick form, as his own call.
* **Every suggestion is stored and settled,** including the ones nobody acts on. Otherwise
  the AI's record means nothing.
* **The market is the baseline to beat.** The odds board already works out a
  margin-free fair price. The AI is only useful if its suggestions beat the closing
  price, which we already measure for Ivo's picks.

### Step 1: a richer match bundle (API-Football Pro, no AI yet)
The AI is only as good as its inputs, and these are mostly what Pro pays for:
* `/predictions?fixture=` gives API-Football's own percentages and comparison (a second baseline).
* `/teams/statistics?league&season&team` gives home/away splits, goals by minute, clean sheets, failed to score, cards.
* `/odds?fixture=` gives extra markets: both teams to score, correct score, Asian handicap, corners, cards. They're included in Pro's quota and cover what The Odds API's free tier can't.
* `/fixtures/lineups?fixture=` gives confirmed line-ups about an hour before kick-off (a separate "Refresh line-ups" button).
* Store these alongside `match_context`, show them on the match page, and include them in `GET /matches/{id}`.
* Refreshing a whole match costs roughly 8–10 requests. Pro allows 7,500 a day, so that's not a constraint.

### Where Claude runs: Microsoft Foundry (decided 2026-10-04, pending model check)
Sam prefers **Claude on Microsoft Foundry** in our Azure subscription, so the AI is
billed and managed alongside everything else (one bill, budget alerts, `rg-football-betting`).
Per-token prices are the same as Anthropic's own API (billed through the Microsoft Marketplace).
* **Client:** `from anthropic import AnthropicFoundry` and `AnthropicFoundry(api_key=..., resource="...")`.
  The rest of the code (`messages.create` / `messages.parse`) is the same, so switching provider later is one line.
  Keep client construction in one place (`app/ai/client.py`).
* **Available on Foundry:** structured outputs, prompt caching, adaptive thinking/effort, web search (basic `web_search_20250305` only).
* **Not available on Foundry:**
  - the **Batch API**, so there's no 50% nightly discount (run analyses one at a time, which is fine at our volume);
  - **server-side `fallbacks`**: use the SDK's client-side `BetaRefusalFallbackMiddleware` instead, and still check `stop_reason`.
* **First task next session:**
  1. Check that `claude-opus-5-5` can be deployed in our subscription/region.
  2. Create the Foundry resource and deployment in `rg-football-betting`.
  3. Put the endpoint/key in App Service settings (`FOUNDRY_RESOURCE`, `FOUNDRY_API_KEY`).
  4. Set an Azure budget alert on the resource group.
* **Fallback option:** the Anthropic API directly (console.anthropic.com), using a
  *separate* organisation for this project with its own billing and spend limit.
  Note that this is not the same as a Claude.ai Pro/Max subscription, which can't power an app.

### Step 2: the analysis call
* **SDK:** `anthropic` (Python), via `AnthropicFoundry` (see above).
* **Model:** `claude-opus-5-5` ($4 / $20 per million input/output tokens). Thinking is always on with this model; set `output_config.effort="high"`, because its default is `medium`.
  Trying `claude-sonnet-5-5` ($2 / $10) to cut cost is Sam's call, not a silent swap.
* **Structured output:** use `client.messages.parse()` with a Pydantic schema, so we always get valid JSON.
  The fields:
  - probabilities for home/draw/away, over/under 2.5 and both teams to score;
  - a list of suggested bets (market, selection, line, minimum acceptable price, stake in units 0.5–3, confidence 1–5, reasoning);
  - key factors;
  - data gaps (e.g. "no line-ups yet");
  - a "no bet" flag, because passing is a legitimate answer.
* **Refusal fallback:** a safety-classifier decline returns `stop_reason: "refusal"`. Always check it before reading the output, and record declines on the run.
  On Foundry use the client-side refusal-fallback middleware. On the Anthropic API directly, use the server-side form instead: `betas=["server-side-fallback-2026-07-01"]` with `fallbacks="default"`.
* **Prompt layout, for caching:**
  - a fixed system prompt written as a versioned file, `backend/app/ai/prompts/v1.md`, containing Ivo's method (see "Open questions");
  - then the match bundle as JSON with sorted keys;
  - cache the system prompt with `cache_control`, and record `prompt_version` on every suggestion.
* **Cost:** a bundle is about 6–10k input tokens, and output plus thinking about 2–4k. That's roughly **$0.08–0.12 per match** on Opus 5.5, so 5 matches a day comes to about $15/month.
  (The Batch API's 50% discount isn't available on Foundry; at a few matches a day that doesn't matter.)
* **Web search:** leave it off at first, so every suggestion can be traced to data we stored.
  Later we could allow `web_search_20260209` restricted to a few news sites for late team news.

### Step 3: storage and settlement
* A new table, `ai_predictions`, with:
  - fixture, model, effort, `prompt_version` and a hash of the bundle;
  - the parsed output as JSON, input/output/cache tokens and cost in USD;
  - `created_at`, plus a link to the background run for progress, the same pattern as syncs.
* Suggested bets go in `tips` with a new `source` column (`ivo` | `ai`) and `published=false`.
  They then settle, and get their closing-price comparison, through the code we already have.
* Probabilities get scored after the match (Brier score / log loss) against two baselines: the bookmakers' fair price and API-Football's prediction.

### Step 4: UI
* **Match page, signed in:** an "Analyse with Claude" button showing the cost estimate and a progress bar, the same pattern as the sync buttons.
  The result panel shows Claude's probabilities next to the fair price, the suggested bets with "Use this" (it opens the existing pick form pre-filled), key factors and data gaps.
* **Admin → AI tab:**
  - the AI's record vs Ivo's vs the market, as a hypothetical P/L, return on stake, strike rate, closing-price comparison and Brier score;
  - spend this month against a budget (`AI_MONTHLY_BUDGET_USD`, with the analyse button refusing to run once it's used up);
  - the recent analyses.

### Step 5: checking it works
* Before trusting it, run it on about 30 already-settled matches from this season and compare it with the market's fair price.
* Use only matches played after the model's training cutoff, so it can't "remember" the result.

### Open questions for Sam and Ivo
1. **Ivo's method in his own words:** what he looks at first, what makes him bet or pass, his staking and price thresholds. This becomes the system prompt, so it's the single most important input.
2. **Monthly AI budget** (suggest $20 to start).
3. **Opus 5.5 vs Sonnet 5.5:** default to Opus 5.5, and compare once there's a track record.
4. **Should AI suggestions ever be visible publicly** (e.g. "Ivo vs the AI")? Default: no.
