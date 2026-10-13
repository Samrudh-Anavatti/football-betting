# Database: where it stands, backups, and when to move

_Written 2026-10-13, after the 2026-10-12 outage. Decision: **nightly backups to Blob storage (done 2026-10-13);
stay on SQLite until there's a concrete reason to move.**_

## Today

* SQLite, one file at `/home/data/football.db` on App Service's persistent disk. `/home` is a **network share**
  (Azure Files), not local disk. It survives restarts and deploys.
* Size on 2026-10-12: **45.6 MB** after about ten days (plus a write log, since removed).
* Rollback journal (`SQLITE_JOURNAL_MODE`, default `DELETE`), and only the process holding the `schedule_lease`
  row in `settings` runs the refresh schedule. Both came out of the outage below.
* Backed up nightly to Blob storage, 30 days kept (below).

### What takes the space (measured 2026-10-12)

| Table | Rows | Size | Per row |
|---|---|---|---|
| `market_books` (every market, latest book per match, kept as the closing book) | 291 | 24.3 MB | 83 KB |
| `ai_messages` (every model message, replayed for follow-ups) | 270 | 7.2 MB | 27 KB |
| `ai_threads` (the bundle each analysis was given) | 65 | 5.1 MB | 78 KB |
| `odds_snapshots` (result/totals/BTTS price history) | 49,907 | small | |
| `match_context`, `ai_predictions`, `leagues`, `sync_runs` | | ~1 MB | |

**Growth estimate with the schedule and 41 leagues:** a few hundred MB a month. Most of it is
AI analyses (~1,100 a month × ~180 KB with the bundle stored twice: in `ai_threads.bundle_json` and again in the
first `ai_messages` row), then market books (~550 main-league matches × 83 KB, plus supplementary ones, which carry
fewer bookmakers). That's roughly 3–4 GB a year. SQLite handles that easily; App Service B1's `/home` quota is
10 GB, so it's about two years of headroom. Storing the bundle once instead of twice would cut AI growth by
about 40%.

## The 2026-10-12 outage

Every query failed with `sqlite3.DatabaseError: file is not a database` and the site went down.

* **Cause.** SQLite was in WAL mode, which keeps a shared-memory index (`football.db-shm`) that every process
  writing the file must share. Processes can't share memory over a network share. Every deploy runs the old and
  new app side by side for a minute or two, and since the refresh schedule (2026-10-12) each of them writes
  every minute. Their views of the write log drifted apart until reads made no sense.
* **Recovery.** Stopped the app, downloaded `football.db`, `-wal` and `-shm` from Kudu
  (`/api/vfs/data/...`), opened them locally: `integrity_check` was ok and the write log folded in cleanly.
  Uploaded the single file, deleted `-wal`/`-shm`, started the app. Nothing of ours was lost (15 settled picks,
  +85.29 units, 67 AI analyses, all fixtures). Only a few minutes of scheduled syncs, which re-ran.
* **Fix.** Rollback journal instead of WAL (file locks, which the share supports) and a lease so one process runs
  the schedule. The damaged originals are in the local scratch folder of the session that fixed it, not in the repo.

## Nightly backups to Blob storage (live since 2026-10-13)

* **Where:** storage account `stfootballbettingsa` (`rg-football-betting`, UK South, Standard LRS, Hot), private
  container `db-backups`. Shared-key access is off, so everything signs in with Entra ID. A lifecycle rule
  (`delete-after-30-days`) removes blobs 30 days after they were written.
* **Who can get in:** the web app's system-assigned managed identity has *Storage Blob Data Contributor* on the
  container only. Sam's account has *Storage Blob Data Reader* on it, for listing and downloading.
* **What runs:** `services/backup.py`, as the scheduler's `backup` job daily at 03:00 UTC (retried hourly if it
  fails) and from **Back up now** on the Schedule card. It copies the database with SQLite's online backup API into
  `/tmp`, gzips it and uploads `football-YYYY-MM-DD-HHMM.db.gz`. App setting: `BACKUP_CONTAINER_URL`
  (`https://stfootballbettingsa.blob.core.windows.net/db-backups`). Unset = no backups.
* **Size:** 13.5 MB compressed for an 83.5 MB database (2026-10-13). 30 of those ≈ 0.4 GB ≈ **£0.01/month**.
* **Tested:** the first 03:00 backup was downloaded, decompressed and checked: integrity ok, all tables and Ivo's
  record (15 settled, +85.29 units) present.

### Restoring

1. Pick a backup:
   `az storage blob list --account-name stfootballbettingsa -c db-backups --auth-mode login -o table`
2. Download and unpack it (into a scratch folder, not the repo):
   `az storage blob download --account-name stfootballbettingsa -c db-backups --auth-mode login -n <name> -f football.db.gz`,
   then gunzip it to `football.db`. Check it: `sqlite3 football.db "pragma integrity_check"` (or Python's `sqlite3`).
3. `az webapp stop -g rg-football-betting -n football-betting-api-sa`
4. Upload it over the live file through Kudu: `PUT https://football-betting-api-sa.scm.azurewebsites.net/api/vfs/data/football.db`
   with headers `Authorization: Bearer $(az account get-access-token --query accessToken -o tsv)` and `If-Match: *`.
   Delete `football.db-journal` (and any `-wal`/`-shm`) the same way with `DELETE`.
5. `az webapp start ...`, then check the site and the Schedule card. Anything since the backup is lost; the
   schedule re-syncs provider data on its own, but picks, bets and AI analyses made since then are gone.

## Later: Azure Database for PostgreSQL

**Move when one of these is true:** more than one app instance; we want to browse and query the live data from a
tool (portal, VS Code, pgAdmin, DBeaver); the file grows past a few GB; or we want managed point-in-time
restore instead of nightly copies.

**Cost** (Azure retail prices, UK South, 2026-10-13):

| Option | £/month | Verdict |
|---|---|---|
| Postgres Flexible Server, Burstable **B1ms** (1 vCore, 2 GB) | **~£13–14**: £10.44 compute (£0.0143/h) + ~£3 for the minimum 32 GB storage; 7 days of backups included | The one to pick |
| Azure SQL Database free offer | £0 on paper | Won't work: its free compute assumes the database sleeps when idle, and the schedule writes every minute, so the month's allowance would go in days |
| Supabase / Neon free tiers | £0 | A second provider and bill, and the ~500 MB storage caps would be hit within months at our growth |

**Effort:** about 2–3 hours, 15 minutes of downtime.

* Code: the models are plain SQLAlchemy. Set `DATABASE_URL=postgresql+psycopg://…`, add `psycopg[binary]`. Make
  the SQLite-only bits portable: the connection pragmas in `database.py`, `hold_lease()` in
  `services/scheduler.py` (uses `INSERT OR IGNORE`), and `add_missing_columns()` (fine on Postgres, but this is
  the moment to switch to Alembic migrations). Tests can keep running on SQLite.
* Data: a one-off script that reads every table from the SQLite file and bulk-inserts into Postgres in dependency
  order (~50k rows, a few minutes), converts SQLite's 0/1 booleans, then resets each id sequence
  (`setval`) and compares row counts table by table.
* Cutover: stop the app, final copy, set `DATABASE_URL`, start, check the site and the Schedule card. Keep the
  SQLite file for a month as a fallback.
* Then delete `SQLITE_JOURNAL_MODE` notes from HANDOFF.md and update the "Moving the backend" section.
