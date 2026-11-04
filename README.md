# NiñoWatch API

FastAPI, Celery, PostgreSQL, Redis, Alembic, and Meta Muse Spark power the
NiñoWatch El Niño preparedness app. This repository **is the backend**: its
Python project, Dockerfile, Compose file, migrations, app, and tests are all at
the root. The Next.js frontend lives in the sibling `ninowatch-frontend` project.

## Local run

Copy `.env.example` to `.env`, then set `MODEL_API_KEY` and a random
`ADMIN_TOKEN`. Keep `.env` private. From this directory, run:

```bash
docker compose up -d --build
docker compose exec -T api env PYTHONPATH=/srv alembic upgrade head
docker compose exec -T api python -m scripts.seed_regions
curl http://localhost:8000/api/health
```

Start the frontend from its sibling directory with `npm install` and
`npm run dev`. It calls `http://localhost:8000` by default. For hosting, set
frontend `NEXT_PUBLIC_API_URL` to the public HTTPS API URL and backend
`CORS_ORIGINS` to the frontend's public origin.

## Development and checks

```bash
uv sync --locked --group dev
uv run ruff check .
uv run pytest
```

Integration tests need a dedicated `nino_test` database. CI creates it with
`scripts/create_test_db.py`. For the local Compose stack, set
`TEST_DATABASE_URL=postgresql+asyncpg://nino:nino@localhost:5433/nino_test`.

## Production notes

Set `MODEL_API_KEY`, `ADMIN_TOKEN`, `DATABASE_URL`, `REDIS_URL`, and
`CORS_ORIGINS` in the deployment environment. Run Alembic before serving
traffic and upsert regions after migrations. Serve the API through HTTPS.
Compose binds the API, Postgres, Redis, and Flower to localhost. The API uses
port 8001 and Flower uses port 5556 on the VPS, so Caddy should proxy the API
to port 8001 without exposing the other services publicly.

### One-time VPS setup for automatic deployment

Install Docker with Compose, Git, and curl, and give the deployment user access
to Docker. Clone this repository into `$HOME/nino_watch`. Create
`$HOME/nino_watch/.env` from `.env.example` on the VPS. Set a strong
`POSTGRES_PASSWORD` before the first database start, and set `DATABASE_URL`
to `postgresql+asyncpg://nino:<same-password>@db:5432/nino`. Use an
alphanumeric password so the URL needs no escaping. Set `MODEL_API_KEY`,
`ADMIN_TOKEN`, and `CORS_ORIGINS` to the real frontend origin. Keep this file
on the VPS; it is ignored by Git.

Add these GitHub Actions repository secrets:

- `VPS_HOST`: VPS address.
- `VPS_USER`: deployment username.
- `VPS_SSH_KEY`: private SSH key whose public key is in that user's
  `~/.ssh/authorized_keys`.
- `VPS_HOST_KEY`: the VPS's verified public SSH host key. A raw
  `ssh-ed25519 AAAA...` line or a full `known_hosts` line works; a
  `SHA256:...` fingerprint alone does not.

On each push to `main`, CI must pass before the deploy job connects over SSH,
checks out the exact tested commit, builds the services, applies migrations,
upserts regions, restarts the stack, and checks `/api/health`. Pull requests
run CI only. The deployment uses SSH port 22 and expects the checkout at
`$HOME/nino_watch` on the VPS.

Only the two pilot regions currently ingest news feeds. The six outlook areas
are curated from linked WMO publications. Seasonal outlooks are regional
signals, not incident predictions or local forecasts. Machine translated
advisories are labeled previews until a speaker reviews them. Community
reports require admin approval before public display and do not affect
verification labels. Broadcaster packs use English until a language is reviewed.

Review pending reports with `GET /api/admin/reports` and a bearer `ADMIN_TOKEN`,
then `POST /api/admin/reports/{id}/review` with
`{"decision":"approved"}` or `{"decision":"rejected"}`.
