# Handoff: operations notes

> **No secrets in here** (the repo is public). Passwords and API keys live only in
> Azure App Service settings.

_Last updated: 2026-10-03 (first prototype deployed)._

## Live resources

| Thing | Value |
|---|---|
| Frontend | https://samrudh-anavatti.github.io/football-betting/ (GitHub Pages, deploys on push to `main`) |
| Backend | https://football-betting-api-sa.azurewebsites.net (API base `/api/v1`, docs at `/docs`) |
| Resource group | `rg-football-betting` (UK South), **separate from PongPoints** |
| App Service plan | `plan-football-betting`, Linux **B1**, Always On |
| Web app | `football-betting-api-sa`, Python 3.11, startup `bash startup.sh` |
| Database | SQLite at `/home/data/football.db` (persists across deploys) |
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
| `API_FOOTBALL_MIN_INTERVAL` | 6.5 | Seconds between API-Football calls (free plan: 10/min). Set 0.2 on a paid plan. |
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

## Gotchas

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

* [ ] Add both API keys as app settings and run the first sync.
* [ ] Confirm API-Football's free plan serves season 2026; if not, decide on Pro ($19/mo).
* [ ] Check the Odds API sport keys for Turkey/Belgium/Portugal match ("0 events" = wrong key or off-season).
* [ ] LLM analysis per match (see DESIGN.md → Next: LLM).
* [ ] Price-movement chart from odds history; closing-line value per pick.
