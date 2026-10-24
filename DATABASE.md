# Database: Azure Database for PostgreSQL

_Moved from SQLite on 2026-10-24. The app had slowed to 15 s for a fixture list: SQLite's file sat on App Service's
`/home`, a network share, and every read went over it. The same request now takes under a second._

## Today

| | |
|---|---|
| Server | `pg-football-betting-sa` (`rg-football-betting`, UK South), Flexible Server, Burstable **B1ms** (1 vCore, 2 GB), PostgreSQL **17**, 32 GB storage |
| Database | `football`, admin user `fbadmin`. The password is only in the web app's `DATABASE_URL` setting. |
| Connection | `DATABASE_URL=postgresql+psycopg://fbadmin:<pw>@pg-football-betting-sa.postgres.database.azure.com:5432/football?sslmode=require` |
| Network | Public endpoint, TLS required, firewall rules for the web app's 31 possible outbound IPs only (`webapp-1`…`webapp-31`). No "allow all Azure services". |
| Backups | Azure's own: automatic, point-in-time restore to any second in the last **35 days** (no extra cost: backup storage up to the provisioned 32 GB is included). |
| Cost | ~£13–14/month: £10.44 compute (£0.0143/h) + ~£3 storage. |

The app pools connections (`pool_size=5`, `pre_ping`, see `database.py`). On Postgres every `String(n)` column is
an unbounded `VARCHAR`, because SQLite never enforced the lengths and provider names can be longer than we guessed.
Local development, the demo data (`python -m app.demo`) and the tests still use SQLite when `DATABASE_URL` is unset;
the tests also pass on Postgres (`DATABASE_URL=... pytest`, an empty database).

**Schema changes** still go through `add_missing_columns()` at startup: new tables and new nullable/defaulted
columns only. Anything harder (renames, type changes, backfills) needs Alembic, which isn't set up yet.

### Querying it

To browse the data (pgAdmin, DBeaver, VS Code, `psql`), add your IP for the session and remove it after:

```
az postgres flexible-server firewall-rule create -g rg-football-betting -n pg-football-betting-sa --rule-name temp-<you> --start-ip-address <ip> --end-ip-address <ip>
az postgres flexible-server firewall-rule delete -g rg-football-betting -n pg-football-betting-sa --rule-name temp-<you> --yes
```

The password: `az webapp config appsettings list -g rg-football-betting -n football-betting-api-sa --query "[?name=='DATABASE_URL'].value" -o tsv`.

If the web app's outbound IPs ever change (a move to another plan or region), add the new ones:
`az webapp show -g rg-football-betting -n football-betting-api-sa --query possibleOutboundIpAddresses`.

### Restoring

Point-in-time restore creates a **new** server; the old one is untouched.

1. `az postgres flexible-server restore -g rg-football-betting -n pg-football-betting-restore --source-server pg-football-betting-sa --restore-time 2026-10-24T13:00:00Z`
2. Add the firewall rules to it (they aren't copied), then point `DATABASE_URL` at the new host and restart the app.
3. Once it's checked, delete the old server, or rename by restoring again. Anything after the restore time is
   lost; the schedule re-syncs provider data, but picks, bets and AI analyses made since then are gone.

## What takes the space

At the move: 1.13M `odds_snapshots` rows (result/totals/BTTS price history), 1,072 `market_books` (~83 KB each,
the full book per match), ~600 AI analyses (`ai_threads` + `ai_messages`, ~180 KB each with the bundle stored twice),
14,914 fixtures. The SQLite file was 390 MB after three weeks. Expect a few hundred MB a month, so 32 GB is years of
headroom. Storing the AI bundle once instead of twice would cut AI growth by about 40%.

## The move (2026-10-24), for the record

* **Code:** `psycopg[binary]`, a pooled engine, portable SQL for the schedule lease (`ON CONFLICT`, `substr`), and
  fixes for queries that were cheap on a local file but not over a network: fixture lists fetched the latest prices
  with one query per fixture (now one query, match-result rows only) and loaded teams/leagues row by row (now
  `selectin`), and the track record parsed every match's ~100 KB market book on each request (tips now store their
  closing price once the match starts).
* **Data:** `python -m app.copy_to_postgres <sqlite file>` (in the repo; it refuses a non-empty target without
  `--replace`). Rehearsed on local Postgres 17 and on the Azure server first. Cutover: a consistent snapshot on the
  server through Kudu (`sqlite3 football.db ".backup cutover.db"`), downloaded, checked (`integrity_check` ok),
  copied (all 16 tables, row counts equal, 51 s), `DATABASE_URL` set, restart. The site stayed readable throughout.
  Afterwards the old file was checked for anything written after the snapshot: no picks, bets or AI analyses, only
  7 minutes of scheduled fetches, which re-ran.
* **Retired:** the nightly SQLite backups to Blob storage (`services/backup.py`, the Schedule card's **Back up
  now**, `BACKUP_CONTAINER_URL`), replaced by Azure's own backups. The storage account `stfootballbettingsa` and
  the old `/home/data/football.db` are kept until **2026-11-07** as a fallback, then deleted.

### Falling back to SQLite (until 2026-11-07)

Remove the `DATABASE_URL` app setting and restart: the app opens `/home/data/football.db` again, as it was at
14:00 UTC on 2026-10-24. Anything written to Postgres since is not in it.

## The 2026-10-12 outage (SQLite, kept for the record)

Every query failed with `sqlite3.DatabaseError: file is not a database`. SQLite was in WAL mode, whose
shared-memory index can't be shared over a network share, and every deploy runs the old and new app side by side
while both wrote every minute. The files were intact; recovered by folding the write log in locally and
re-uploading. The fix then was the rollback journal and the schedule lease. The lease stays on Postgres: deploys
still overlap two processes, and only the lease holder runs the schedule.
