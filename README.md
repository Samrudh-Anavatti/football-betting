# ⚽ Football Betting (Ivo's Picks)

A site for Ivo's football betting picks. The public side shows his open picks and
a settled track record, plus upcoming fixtures and results across 12 competitions.
The signed-in side is where Ivo and Sam pull data from the providers, research a
match (bookmaker prices, form, H2H, injuries, league table), publish picks by
clicking a price, and track virtual-money bankrolls.

See [DESIGN.md](DESIGN.md) for how it fits together, and [HANDOFF.md](HANDOFF.md)
for live resources, config and operations.

## Stack

| Layer    | Choice |
|----------|--------|
| Frontend | React + Vite + Tailwind + React Router (HashRouter) on GitHub Pages |
| Backend  | FastAPI + SQLAlchemy 2.0 + SQLite on Azure App Service (Linux, B1, UK South) |
| Data     | [API-Football](https://www.api-football.com/) (fixtures, results, tables, H2H, form, injuries) and [The Odds API](https://the-odds-api.com/) (bookmaker prices) |
| Auth     | Username + password per person (bcrypt) → signed token (JWT) |

## Project layout

```
backend/
  app/
    providers/   API clients (one per provider). Track quota from response headers.
    services/    sync jobs, odds↔fixture matching, settlement, odds board, stats
    routers/     public.py (read-only, cached data) and admin.py (signed in)
    demo.py      local demo data (no API keys needed)
  tests/         end-to-end flow against fake providers + unit tests
frontend/
  src/pages      Home, Fixtures/Results, Match, Admin
  src/components OddsBoard, PickForm, TipCard, admin/DataTab etc.
.github/workflows  Pages deploy + Azure backend deploy (tests gate both)
```

## Run locally

Two terminals.

### Backend (http://localhost:8000, docs at /docs)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows; source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
copy .env.example .env            # then paste API keys in, or leave blank
python -m app.demo                # optional: fake fixtures, prices and a couple of picks
uvicorn app.main:app --reload
pytest -q                         # tests
```

Local sign-in: `sam` / `changeme` or `ivo` / `changeme` (set by `PASSWORD_<NAME>` in `.env`).

### Frontend (http://localhost:5173)

```bash
cd frontend
npm install
npm run dev                       # proxies /api to localhost:8000
```

## Using it

1. **Admin → Data → Sync fixtures and results.** Pulls each league's whole season
   in one request per league (+1 for the table). Weekly is enough, plus after a
   matchday to settle picks.
2. **Admin → Data → Pull prices.** One Odds API call per league; cost is shown
   before you click.
3. **Open a match → Refresh research** for H2H, last five and injuries (4–6
   requests), then **click any price** to publish it as a pick or log a virtual bet.
