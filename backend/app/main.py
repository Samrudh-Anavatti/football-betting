"""FastAPI application entrypoint."""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .database import Base, SessionLocal, add_missing_columns, engine
from .routers import admin, ai, public
from .seed import sync_users
from .services.sync import ensure_leagues, fail_interrupted_runs

app = FastAPI(title="Football Betting API", version="0.1.0")

_origins = os.getenv("CORS_ORIGINS", "*")
allow_origins = ["*"] if _origins.strip() == "*" else [o.strip() for o in _origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Match boards with every market run to a few hundred KB of JSON; it compresses ~10x.
app.add_middleware(GZipMiddleware, minimum_size=2000)

app.include_router(public.router, prefix="/api/v1")
app.include_router(admin.auth_router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(ai.router, prefix="/api/v1")


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    add_missing_columns()
    sync_users()
    db = SessionLocal()
    try:
        ensure_leagues(db)
        fail_interrupted_runs(db)
    finally:
        db.close()


@app.get("/api/v1/health", tags=["meta"])
def health():
    return {"status": "ok"}
