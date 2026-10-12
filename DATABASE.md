# Database: where it stands, backups, and when to move

_Written 2026-10-13, after the 2026-10-12 outage. Decision then: **add nightly backups to Blob storage soon; stay
on SQLite until there's a concrete reason to move.**_

## Today

* SQLite, one file at `/home/data/football.db` on App Service's persistent disk. `/home` is a **network share**
  (Azure Files), not local disk. It survives restarts and deploys.
* Size on 2026-10-12: **45.6 MB** after about ten days (plus a write log, since removed).
* Rollback journal (`SQLITE_JOURNAL_MODE`, default `DELETE`), and only the process holding the `schedule_lease`
  row in `settings` runs the refresh schedule. Both came out of the outage below.
* **No backups.** The file is the only copy of Ivo's track record, the bets and the AI's record.

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

## Next: nightly backups to Blob storage (~£0.01/month, ~30 min to build)

1. **Storage account** in `rg-football-betting`, UK South, Standard LRS, a private container `db-backups`.
   Lifecycle rule: delete blobs older than 30 days.
2. **Access without keys:** turn on the web app's system-assigned managed identity and give it
   *Storage Blob Data Contributor* on that container. Add `azure-identity` and `azure-storage-blob` to
   `requirements.txt`, and an app setting `BACKUP_CONTAINER_URL`
   (`https://<account>.blob.core.windows.net/db-backups`).
3. **A scheduler job,** daily at about 03:00 UTC (quiet: no matches), shown on the Schedule card like the others:
   * take a consistent copy with SQLite's online backup API (`sqlite3.connect(src).backup(dest)`) into `/tmp`
     (local disk; never copy the live file byte by byte);
   * gzip it (~45 MB → roughly 10–15 MB);
   * upload as `football-YYYY-MM-DD.db.gz`;
   * record the run (size, duration) as a SyncRun so a failure shows on the card.
4. **Cost:** 30 copies × ~15 MB ≈ 0.5 GB at ~£0.014/GB/month (Hot LRS, UK South) ≈ **£0.01/month**, plus
   negligible transaction charges.
5. **Restore** (document it in HANDOFF.md once built): download the blob, gunzip, stop the app, upload to
   `/home/data/football.db` through Kudu (`PUT /api/vfs/data/football.db` with `If-Match: *`), delete any
   `football.db-journal`, start the app.
6. Test the restore once, on a local copy, before relying on it.

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
