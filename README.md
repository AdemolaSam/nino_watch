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
The Compose file is a local development stack; replace its example database
credentials and exposed service ports for a VPS.

Only the two pilot regions currently ingest news feeds. The six outlook areas
are curated from linked WMO publications. Seasonal outlooks are regional
signals, not incident predictions or local forecasts. Machine translated
advisories are labeled previews until a speaker reviews them. Community
reports require admin approval before public display and do not affect
verification labels. Broadcaster packs use English until a language is reviewed.

Review pending reports with `GET /api/admin/reports` and a bearer `ADMIN_TOKEN`,
then `POST /api/admin/reports/{id}/review` with
`{"decision":"approved"}` or `{"decision":"rejected"}`.
