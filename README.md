# TripWeave

Constraint-aware multi-stop trip planner. Pick places, set dates, daily windows, durations, budget and
constraints; TripWeave builds a day-by-day itinerary with a real optimizer (Google OR-Tools), shows it on a
map and timeline, lets you edit it by hand, and re-optimizes without throwing your edits away.

**Works without any paid API.** With no routing service configured, the optimizer orders stops by
straight-line distance and says so everywhere in the UI. It never presents that as a route or travel time.

| Layer | Tech |
|---|---|
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4, Leaflet |
| Backend | Python 3.13, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic |
| Database | PostgreSQL (PostGIS image in Compose; spatial column added only when the extension exists). SQLite works for dev/tests. |
| Optimization | OR-Tools routing solver + deterministic heuristic fallback |
| Tests | pytest, Vitest + React Testing Library |

## Quick start (Docker Compose)

```bash
cp .env.example .env          # set SECRET_KEY and POSTGRES_PASSWORD
docker compose up --build
# UI:  http://localhost:8080      API docs: http://localhost:8000/docs
```

The backend container runs `alembic upgrade head`, seeds the curated catalog (idempotent), then starts Uvicorn.

## Local development (no Docker)

```bash
# backend
cd backend
python3 -m venv ../.venv && . ../.venv/bin/activate
pip install -r requirements-dev.txt
export DATABASE_URL=sqlite:///./tripweave.db      # or a postgresql+psycopg:// URL
alembic upgrade head && python -m app.seed
uvicorn app.main:app --reload --port 8000

# frontend (second terminal)
cd frontend && npm install && npm run dev          # http://localhost:5173, proxies /api to :8000
```

## Run the optimizer on its own

No database or network needed:

```bash
cd backend && python -m examples.optimize_demo --days 2 --solver ortools
python -m examples.optimize_demo --solver fallback
python -m examples.optimize_demo --osrm-url http://localhost:5000   # real routing, if you run OSRM
```

Architecture and tuning: [docs/optimization.md](docs/optimization.md).

## Features

- Create/edit/delete trips: destination, dates, travellers, daily window, travel mode, budget + currency,
  max daily workload, max travel per day, max single leg, start/end points, interests, accessibility notes.
- Place catalog (curated Paris and Rome landmarks) with provenance; add private custom places with optional
  cost (+currency) and opening hours (**source required**).
- Per-trip place choices: must-visit / optional / excluded, interest 1-5, visit minutes, hours override, pin to day.
- Optimizer: selection, matrix acquisition, validation, OR-Tools solve, schedule construction, independent
  result validation, explanation. Reports unscheduled stops and infeasible constraints.
- Itinerary editor: reorder, move between days, edit duration/notes, add/remove stops, "Keep here" lock,
  manual-vs-optimized indicators, recompute times, preview, re-optimize, explicit confirmation before
  replacing manual edits, before/after comparison, warnings.
- Map: numbered markers per day, selection synced with the list, graceful tile-failure notice, dashed
  "visit order" line explicitly labelled as not a route.
- Budget: user-entered expenses, planned admission from recorded costs x travellers, Decimal-safe totals,
  currencies kept separate unless a conversion provider is configured.
- Save/reopen (everything persists server-side), export as JSON, CSV, ICS.
- Auth with per-user private trips (other users get 404).

## What depends on external services

| Feature | Needs | Without it |
|---|---|---|
| Road/walking travel times and distances | OSRM-compatible `/table` service (`ROUTING_PROVIDER=osrm`, `OSRM_BASE_URL`) | Straight-line *estimates* (ordering only), your transit buffer used for scheduling |
| Currency conversion | `FX_PROVIDER=frankfurter` (public ECB-rate API, no key) | Currencies listed separately, no combined total |
| Map tiles | `MAP_TILE_URL` (default: OSM tile server) | Notice shown; markers and lists still work |
| PostGIS spatial column | PostGIS-enabled Postgres | Skipped automatically; lat/lon columns are the source of truth |
| Weather | **Not implemented** | n/a |

Data sources and attribution: [docs/data-sources.md](docs/data-sources.md).

## Tests and checks

```bash
cd backend
pytest -q                                      # SQLite
TEST_DATABASE_URL=postgresql+psycopg://user:pw@localhost/tripweave_test pytest -q   # PostgreSQL
ruff check . && ruff format --check . && mypy app

cd ../frontend
npm run typecheck && npm run lint && npm test && npm run build
```

## Documentation

- [docs/api.md](docs/api.md): endpoints (live OpenAPI at `/docs`)
- [docs/optimization.md](docs/optimization.md): optimizer architecture, honesty rules, limitations
- [docs/data-sources.md](docs/data-sources.md): catalog provenance and attribution
- [docs/deployment.md](docs/deployment.md): manual deployment steps and environment variables

## Known limitations

See the end of [docs/optimization.md](docs/optimization.md#limitations).
