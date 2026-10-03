#!/usr/bin/env bash
# Azure App Service startup script — launches the FastAPI app with uvicorn.
# App Service provides $PORT; fall back to 8000 for local use.
python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
