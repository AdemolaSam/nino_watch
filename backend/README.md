# NiñoWatch backend

FastAPI + Celery + Postgres + Redis. See `/BACKEND.md` (repo root) for the full spec.

## Quick start

```bash
cp .env.example .env
docker compose up --build
curl localhost:8000/api/health
```

Local dev without Docker (needs local Postgres 16 + Redis 7):

```bash
uv sync --group dev
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

## Commands

```bash
uv run pytest
uv run ruff check .
uv run alembic upgrade head
```

## Status

- B0 scaffold: done (compose stack green, `/api/health` ok, alembic at head).
- B1 LLM layer: done (client/router/cache/parse-retry/`llm_calls`/fake+echo, smoke script writes 10/10 languages). Live Meta API call still needs `MODEL_API_KEY`.
- B2 regions + incidents: done (3 region YAMLs, seed script, live endpoints verified).
- B3 ingest: done (4 real feeds verified + ingesting 100 articles into dev DB; robots + crawl-delay honored; beat every 45 min).
- B4 extraction + geocoding: done (prompt v1, extract service with retry policy, GeoNames cities500 + Nominatim fallback, 30-label eval committed with echo baseline; real-model run needs `MODEL_API_KEY`).
- B5 clustering: done (type+50km+±2d grouping, syndication/ownership collapse, pure domain funcs + beat every 15 min).
- B6 weather: done (Open-Meteo plausibility + cached climate grids, live-verified 216/384 cells; retry/backoff on 429).
- B7 verification: done (deterministic labels, official-stance + same-event signals, merge pass; label matrix tested).
- B8 advisory: done (grounded EN + cached translations + gating; live-verified, echo-seeded demo rows are FAKE-marked).
- B9 outlet pack: done (radio 65-75w + SMS segment validators with retry; packs chain off advisory generation).
- B10 polish: done (unified `{error:{code,message}}`, CORS origin-only, `openapi.json` export; TS gen via `npx openapi-typescript openapi.json -o lib/api-types.ts` in the frontend repo).
- B11 smoke: done (`scripts/smoke.py`, 11/11 checks, wired in CI).
- B12 deploy: manual (no VPS here). `docker compose up --build` + `alembic upgrade head` + `seed.py` + `seed_geonames.py`, then terminate TLS in front (Caddy/nginx) and set `CORS_ORIGINS` to the real frontend origin.
- Stretch S1–S4: cut (see BACKEND.md section 14 cut order).

## Demo notes

- Without `MODEL_API_KEY`, the pipeline runs but produces no real LLM output: extraction leaves articles pending, advisories/packs 503. The dev DB holds echo-seeded advisories whose every field starts with `[FAKE ...]` (demo scaffolding only).
- No language is marked tested (no fluent review yet), so `?lang=ha` etc. correctly return English with `available: false`.
- The "review before broadcast" and machine-translation labels are frontend display concerns: the pack artifacts stay clean for air by design.

## Seed the dev database

```bash
DATABASE_URL=postgresql+asyncpg://nino:nino@localhost:5433/nino uv run alembic upgrade head
DATABASE_URL=postgresql+asyncpg://nino:nino@localhost:5433/nino uv run python scripts/seed.py
```

Integration tests use a separate `nino_test` database (auto-created by `scripts/create_test_db.py`, wired in CI):

```bash
TEST_DATABASE_URL=postgresql+asyncpg://nino:nino@localhost:5433/nino_test uv run pytest
```
