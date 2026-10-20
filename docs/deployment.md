# Deployment (manual)

Nothing is deployed automatically. Any host that runs Docker Compose, or Postgres + Python + static hosting, works.

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `SECRET_KEY` | **yes (prod)** | JWT signing key; use >= 32 random bytes |
| `DATABASE_URL` | yes | `postgresql+psycopg://user:pw@host:5432/db` (set by Compose) |
| `POSTGRES_PASSWORD` | Compose | DB password |
| `CORS_ORIGINS` | if UI on another origin | comma-separated |
| `ACCESS_TOKEN_MINUTES` | no | default 720 |
| `ROUTING_PROVIDER` / `OSRM_BASE_URL` / `ROUTING_TIMEOUT_S` / `ROUTING_MAX_POINTS` | no | real routing |
| `FX_PROVIDER` / `FX_BASE_URL` | no | currency conversion |
| `MAP_TILE_URL` / `MAP_TILE_ATTRIBUTION` | no | tile provider |

## Docker Compose on a server

1. `git clone <repo> && cd TripWeave`
2. `cp .env.example .env`; set `SECRET_KEY` (`python -c "import secrets;print(secrets.token_urlsafe(48))"`), `POSTGRES_PASSWORD`, `CORS_ORIGINS`.
3. `docker compose up -d --build` (runs migrations and seeds the catalog).
4. Put a TLS-terminating reverse proxy (Caddy/nginx/Traefik) in front of port 8080 (UI + `/api` proxy).
5. Back up the `dbdata` volume (`pg_dump`).
6. Upgrades: `git pull && docker compose up -d --build` (migrations run on start).

## Without Docker

1. Provision PostgreSQL 14+ (PostGIS optional). Create DB and user.
2. Backend: `pip install -r backend/requirements.txt`; export env; `cd backend && alembic upgrade head && python -m app.seed`;
   run `uvicorn app.main:app --host 0.0.0.0 --port 8000` under a process manager (systemd).
3. Frontend: `cd frontend && npm ci && npm run build`; serve `dist/` statically and proxy `/api/` to the backend (see `frontend/nginx.conf`).

## Optional OSRM

Run your own OSRM (see the OSRM project docs: extract + contract an OSM extract for your region, then `osrm-routed`), set `ROUTING_PROVIDER=osrm`,
`OSRM_BASE_URL=http://osrm:5000`. If it is down or returns invalid data, TripWeave falls back to labelled straight-line estimates and notes it in the plan.

## Production checklist

* Strong `SECRET_KEY`, HTTPS, restricted `CORS_ORIGINS`.
* Own tile provider (OSM public tiles are not for heavy use).
* No rate limiting or email verification is built in; add them at the proxy/identity layer if the app is public.
