# Handoff: operations notes

> **No secrets in here** (the repo is public). Passwords and API keys live only in
> Azure App Service settings.

_Last updated: 2026-10-07 (prices now come from API-Football for every market; AI analysis on Microsoft Foundry, switched from Claude Sonnet 5.5 to **GPT-5.6 Luna** the same day; **next: Ivo's method for the prompt**)._

## Live resources

| Thing | Value |
|---|---|
| Frontend | https://samrudh-anavatti.github.io/football-betting/ (GitHub Pages, deploys on push to `main`) |
| Backend | https://football-betting-api-sa.azurewebsites.net (API base `/api/v1`, docs at `/docs`) |
| Resource group | `rg-football-betting` (UK South), **separate from PongPoints** |
| App Service plan | `plan-football-betting`, Linux **B1**, Always On |
| Web app | `football-betting-api-sa`, Python 3.11, startup `bash startup.sh` |
| Database | SQLite at `/home/data/football.db` (persists across deploys) |
| AI | Foundry resource `foundry-football-sa` (AIServices, **Sweden Central**). Deployment **`gpt-5.6-luna`** (version 2026-07-09, Global Standard, capacity 200 = 200k tokens/min), used by the app. The `claude-sonnet-5-5` deployment was deleted on 2026-10-07 (no Marketplace/SaaS resources were left behind). No fallback model: if Luna is down, analysis waits. |
| Budget alert | `football-betting-monthly` on the resource group: 50 (billing currency) a month, emails at 80% actual and 100% forecast. |
| Plans | API-Football **Pro** ($19/mo, 7,500 req/day, upgraded 2026-10-03 for a one-month trial). The Odds API **free** (500 credits/month), now only a backup. |
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
| `ODDS_BOOKMAKERS` | 8,7,3,36,4 | API-Football bookmaker ids kept on the board: Bet365, William Hill, Betfair, BetVictor, Pinnacle. Ids from `/odds/bookmakers`. Swap when the affiliate deals are decided. |
| `FOUNDRY_RESOURCE` / `FOUNDRY_API_KEY` | — | The Foundry resource the AI runs on. Key: `az cognitiveservices account keys list -g rg-football-betting -n foundry-football-sa`. |
| `AI_MODEL` | gpt-5.6-luna | A Foundry deployment name that speaks the Responses API (e.g. `gpt-5.6-terra` after deploying it). Add its price to `AI_PRICES` in `config.py`. |
| `AI_EFFORT` | high | Reasoning effort per call (low / medium / high). |
| `AI_MONTHLY_BUDGET_USD` | 20 | The Analyse/chat buttons refuse once this month's AI spend reaches it. |
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
* [x] Prices for every market from API-Football (2026-10-07). **This makes Pro load-bearing**: dropping it takes the board back to match result and totals from The Odds API.
* [x] AI match analysis built (2026-10-07), see "AI analysis" below. Switched to GPT-5.6 Luna the same day (~10x cheaper, same verdicts in testing).
* [ ] **Ivo's method in his own words** → `backend/app/ai/prompts/v3.md` (copy v2, fill the "Ivo's method" section, bump `PROMPT_VERSION` in `ai/service.py`).
* [ ] Back-test: run the AI on ~30 settled matches played after its training cutoff and compare Brier scores with the market.
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
| GPT-5.6 Luna on Foundry (measured ~$0.01 per match) | ~1–2 even with heavy use |
| Postgres Flexible B1ms (future) | ~10–13 |

About £25–27/month including AI analysis. The resource group's budget alert is set at 50.

## Prices: every market from API-Football (built 2026-10-07)

* API-Football's `/odds` (Pro) carries 100–150 markets per match: result, double chance, draw no bet, goals and
  team goals, halves, HT/FT, exact scores, Asian and European handicaps, corners, cards, offsides, scorers, player
  shots and fouls. We keep five bookmakers (`ODDS_BOOKMAKERS`); Bet365 carries most of the breadth, the others
  mainly the core markets.
* **Admin → Data → Prices, all markets** pulls every upcoming match in the chosen leagues: 1 request per 10 matches
  (EPL: 2). A match page's **Refresh prices** costs 1 request.
* Storage: `market_books` holds the latest full book per match as JSON (~100 KB), frozen at kick-off, so it doubles
  as the closing book. Result, totals and BTTS prices are also appended to `odds_snapshots` (history, fixture list).
* Picks can be made on any market. Result/totals/BTTS are stored as our codes; anything else keeps API-Football's
  market and value names. Auto-settlement covers everything decidable from the full-time and half-time scores
  (result, double chance, draw no bet, goals lines, team totals, BTTS, exact score, HT/FT, halves, odd/even, clean
  sheet, win to nil, result+goals combos). Corners, cards, scorers and Asian quarter lines are settled by hand in
  Admin → Picks.
* The Odds API stays wired in as a backup (Admin → Data, right-hand card). A match page uses it only if it has no
  API-Football book.

## AI analysis (built 2026-10-07)

**Model: GPT-5.6 Luna** (Foundry deployment `gpt-5.6-luna`, OpenAI SDK, Responses API, `store=False` with
encrypted reasoning replayed each turn, so nothing is kept on Azure's side). Chosen over Claude Sonnet 5.5 on cost:

| Arsenal v Leeds, same bundle | Sonnet 5.5 | Luna (high effort) |
|---|---|---|
| Probabilities H/D/A, over 2.5, BTTS | 69/19/12, 52, 46 | 71/18/11, 50, 47 |
| Verdict | no bet | no bet |
| Analysis / follow-up cost | $0.148 / $0.015 | $0.014 / $0.0013 |

Why a cheaper model is enough: in the 2026 World Cup study (arXiv 2607.17765) four frontier models all matched but
didn't beat the bookmakers' probabilities; what separated their betting results was discipline (following vs fading
the market), not intelligence. So the prompt carries the weight. **Prompt v2** (2026-10-07) anchors on the market's
fair probabilities, treats early-season splits as weak evidence, caps suggestions at two uncorrelated bets, and
calls passing the normal outcome; on prompt v1 Luna suggested 4–5 correlated bets a match and moved 10+ points
off the market on 2–3 game samples. Claude-era threads still display but are read-only.

**How it works.** On a match page (signed in), **Analyse with AI** builds the match bundle (the same data as the
page: every market's best and fair price, form, H2H, injuries, season stats, API-Football's prediction, line-ups,
table), starts a conversation, and asks for an analysis. The model records it through a strict `record_analysis` function
(probabilities, suggested bets with minimum prices, stakes, confidence, reasoning, key factors, data gaps, no-bet
flag), then writes a summary. Follow-up questions continue the same conversation: the stored history is resent
unchanged each turn (append-only, thinking blocks included) and prompt caching makes the repeated bundle cheap, so
there is no memory framework to maintain. **Fresh analysis with latest data** starts a new conversation with a
rebuilt bundle; old ones stay readable.

* Code: `backend/app/ai/` (`client.py` is the only place the client is built, `bundle.py`, `service.py`,
  `prompts/v2.md`), endpoints in `routers/ai.py`, UI in `AiPanel.jsx` and Admin → AI. AI runs are SyncRuns with
  provider `claude` (historical name).
* Tables: `ai_threads` (bundle as sent, its hash, model, prompt version), `ai_messages` (every API message as sent and
  received, with tokens and cost), `ai_predictions` (each recorded analysis plus the market's margin-free
  probabilities at that moment).
* **Privacy:** suggestions are never published. Each suggested bet whose best current price is at or above the AI's
  minimum becomes a `tips` row with `source='ai'`, `published=false`, at the best price available then. A new analysis
  replaces the match's earlier pending AI tips. Public endpoints only return `source='ivo'`, published tips.
  "Use this" opens the normal pick form, pre-filled, so a published pick is Ivo's.
* **Scoring:** Admin → AI shows the AI's settled record next to Ivo's (P/L, ROI, strike rate, closing-price
  comparison) and Brier scores for result, over 2.5 and BTTS against the market's fair probabilities, using the
  last analysis before kick-off.
* **Refusals and truncation:** a refusal part or an incomplete response is shown as an error on the run.

**Measured cost (Luna, prompt v2, 4 EPL matches, 2026-10-07).** Bundle ~31k tokens (Luna's tokenizer). An analysis
is two calls (the function call, then the summary, mostly cached): **$0.009–0.015**. A follow-up question ~$0.001.
At that price the $20 monthly budget is about 1,500 analyses.

**Foundry setup gotchas.** (OpenAI models such as Luna deploy with a plain
`az cognitiveservices account deployment create ... --model-format OpenAI`; the below applies to Claude.)
* Claude deployments need `modelProviderData` (organisationName, countryCode, industry in lowercase), which the
  CLI (2.70) can't pass, so deploy through ARM REST, api-version `2025-10-01-preview`:
  `az rest --method put --url .../accounts/foundry-football-sa/deployments/<name>?api-version=2025-10-01-preview --body @deploy.json`
  with `{"sku":{"name":"GlobalStandard","capacity":80},"properties":{"model":{"format":"Anthropic","name":"claude-sonnet-5-5","version":"2"},"modelProviderData":{"organizationName":"Samrudh Anavatti","countryCode":"GB","industry":"other"}}}`.
* The first attempt failed with "This purchase cannot be completed" (Marketplace). Deleting the failed deployment
  and recreating it worked.
* Default capacity 1 means 1 request a minute; set 80 (the quota).

## Running the analysis locally

Copy the prod DB from Kudu (`/api/vfs/data/football.db` plus `-wal`/`-shm`, bearer token from
`az account get-access-token`) into a scratch folder, set `DATA_DIR` to it, the API keys, and
`FOUNDRY_RESOURCE`/`FOUNDRY_API_KEY`, then run uvicorn. Never point local code at `/home/data`.

## AI predictions: original plan (2026-10-04, kept for reference)


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
