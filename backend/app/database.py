"""Database session + engine setup.

A single SQLite file in DATA_DIR (``/home/data`` on App Service, which persists
across deploys). Moving to another host = copy that one file; see HANDOFF.md.
Override with ``DATABASE_URL`` (e.g. Postgres) when we outgrow SQLite.
"""
import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'football.db'}")

_is_sqlite = DATABASE_URL.startswith("sqlite")
_connect_args = {"check_same_thread": False, "timeout": 30} if _is_sqlite else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

if _is_sqlite:
    # WAL lets the site keep reading while a background sync is writing.
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
