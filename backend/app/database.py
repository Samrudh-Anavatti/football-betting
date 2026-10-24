"""Database session + engine setup.

Production runs on Azure Database for PostgreSQL (``DATABASE_URL``, see
DATABASE.md). Without it, a single SQLite file in DATA_DIR: local development,
the demo data and the tests.
"""
import os
from pathlib import Path

from sqlalchemy import String, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'football.db'}")

_is_sqlite = DATABASE_URL.startswith("sqlite")
if _is_sqlite:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False, "timeout": 30})
else:
    # pre_ping drops connections the server closed while idle (Azure closes them after a while).
    engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=10, pool_pre_ping=True, pool_recycle=1800)


@compiles(String, "postgresql")
def _unbounded_varchar(type_, compiler, **kw):
    """String(n) lengths were never enforced on SQLite and provider names can run long,
    so on Postgres every String is an unbounded VARCHAR (same storage as TEXT)."""
    return "VARCHAR"
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

# WAL needs shared memory between processes, which App Service's /home (a network
# share) can't provide: two overlapping processes during a deploy corrupted the
# database's view of itself on 2026-10-12. The default rollback journal locks the
# file instead, which works there. SQLITE_JOURNAL_MODE=WAL is fine on a local disk.
JOURNAL_MODE = os.getenv("SQLITE_JOURNAL_MODE", "DELETE").upper()

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute(f"PRAGMA journal_mode={JOURNAL_MODE}")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


class Base(DeclarativeBase):
    pass


def add_missing_columns() -> None:
    """Tiny forward-only migration: create_all() makes new tables but never alters
    existing ones, so add any model column the live table lacks. Enough for
    nullable/defaulted additions; anything harder needs Alembic (see HANDOFF.md)."""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                ddl = f'ALTER TABLE {table.name} ADD COLUMN "{col.name}" {col.type.compile(engine.dialect)}'
                default = col.default.arg if col.default is not None and not callable(col.default.arg) else None
                if default is not None:
                    ddl += f" DEFAULT {default!r}" if isinstance(default, str) else f" DEFAULT {default}"
                conn.execute(text(ddl))


def get_db():
    """FastAPI dependency: yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
