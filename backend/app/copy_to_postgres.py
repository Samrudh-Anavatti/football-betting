"""One-off copy of the SQLite database into Postgres (the 2026-10 move, see DATABASE.md).

    TARGET_DATABASE_URL=postgresql+psycopg://user:pw@host:5432/football \\
        python -m app.copy_to_postgres path/to/football.db [--replace]

Creates the tables, copies every row in foreign-key order with COPY, resets the
id sequences and compares row counts. Refuses a target that already has rows
unless --replace (which empties it first). The source is opened read-only.
"""
import os
import sqlite3
import sys
import time
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, create_engine, inspect, text

from . import models  # noqa: F401  registers the tables
from .database import Base

BATCH = 5000
SKIP = {"settings": "key = 'schedule_lease'"}  # old lease format; the new process writes its own


def _converter(col):
    if isinstance(col.type, Boolean):
        return lambda v: None if v is None else bool(v)
    if isinstance(col.type, DateTime):
        return lambda v: v if v is None or isinstance(v, datetime) else datetime.fromisoformat(v)
    if isinstance(col.type, Integer):
        return lambda v: v
    # Postgres text can't hold NUL characters; SQLite's can.
    return lambda v: v.replace("\x00", "") if isinstance(v, str) else v


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    replace = "--replace" in argv
    url = os.environ.get("TARGET_DATABASE_URL", "")
    if len(args) != 1 or not url.startswith("postgresql"):
        print(__doc__)
        return 2
    src = sqlite3.connect(f"file:{args[0]}?mode=ro", uri=True)
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    tables = Base.metadata.sorted_tables

    with engine.begin() as conn:
        busy = [t.name for t in tables if conn.execute(text(f'SELECT EXISTS (SELECT 1 FROM "{t.name}")')).scalar()]
        if busy and not replace:
            print(f"Target already has rows in {', '.join(busy)}; rerun with --replace to empty it first.")
            return 1
        if busy:
            conn.execute(text("TRUNCATE " + ", ".join(f'"{t.name}"' for t in tables) + " CASCADE"))

    have_src = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    report = []
    raw = engine.raw_connection()
    try:
        for t in tables:
            if t.name not in have_src:
                report.append((t.name, 0, 0, "not in source"))
                continue
            src_cols = {r[1] for r in src.execute(f'PRAGMA table_info("{t.name}")')}
            cols = [c for c in t.columns if c.name in src_cols]
            extra = src_cols - {c.name for c in t.columns}
            conv = [_converter(c) for c in cols]
            names = ", ".join(f'"{c.name}"' for c in cols)
            where = f" WHERE NOT ({SKIP[t.name]})" if t.name in SKIP else ""
            started, n = time.monotonic(), 0
            cur = src.execute(f'SELECT {names} FROM "{t.name}"{where}')
            with raw.cursor() as pg, pg.copy(f'COPY "{t.name}" ({names}) FROM STDIN') as cp:
                while rows := cur.fetchmany(BATCH):
                    for row in rows:
                        cp.write_row([f(v) for f, v in zip(conv, row)])
                    n += len(rows)
                    print(f"\r  {t.name}: {n:,}", end="", flush=True)
            raw.commit()
            print(f"\r  {t.name}: {n:,} rows in {time.monotonic() - started:.0f}s")
            report.append((t.name, src.execute(f'SELECT count(*) FROM "{t.name}"{where}').fetchone()[0], None,
                           f"source-only columns ignored: {sorted(extra)}" if extra else ""))
    finally:
        raw.close()

    with engine.begin() as conn:
        for t in tables:
            pk = list(t.primary_key.columns)
            if len(pk) == 1 and isinstance(pk[0].type, Integer) and pk[0].autoincrement is not False:
                conn.execute(text(f"SELECT setval(pg_get_serial_sequence('\"{t.name}\"', '{pk[0].name}'), "
                                  f'COALESCE(MAX("{pk[0].name}"), 1), MAX("{pk[0].name}") IS NOT NULL) FROM "{t.name}"'))
        report = [(name, n, conn.execute(text(f'SELECT count(*) FROM "{name}"')).scalar() if name in inspect(conn).get_table_names() else 0, note)
                  for name, n, _, note in report]

    print(f"\n{'table':<16}{'sqlite':>12}{'postgres':>12}")
    ok = True
    for name, a, b, note in report:
        ok &= a == b
        print(f"{name:<16}{a:>12,}{b:>12,}  {'' if a == b else 'MISMATCH '}{note}")
    print("\nAll row counts match." if ok else "\nRow counts differ: do not switch over.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
