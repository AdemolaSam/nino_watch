# NiñoWatch

An El Niño preparedness dashboard with sourced seasonal outlooks, live incident
verification, Meta Muse Spark advisories, local-language previews, and a moderated
community evidence form. The Next.js frontend lives in the sibling
`ninowatch-frontend` directory.

## Run locally

1. Set `MODEL_API_KEY` and `ADMIN_TOKEN` in `backend/.env` (see `.env.example`).
2. From `backend`, run `docker compose up -d --build`.
3. Run `docker compose exec -T api env PYTHONPATH=/srv alembic upgrade head`.
4. Run `docker compose exec -T api python -m scripts.seed_regions`.
5. From `ninowatch-frontend`, run `npm install && npm run dev`.

The API is at `http://localhost:8000`, and the web app is at
`http://localhost:3000`. The frontend uses `NEXT_PUBLIC_API_URL`, defaulting
to that local API URL. Set it to the public HTTPS API URL for deployment.
Set backend `CORS_ORIGINS` to the frontend's public origin. Configure an
HTTPS database and Redis instance for a hosted deployment.

Only the two pilot regions currently ingest news feeds. The six outlook areas
are curated from linked WMO publications. Seasonal outlooks are regional
signals, not incident predictions or local forecasts. Community submissions
remain pending until a reviewer approves them through the admin API, and they
never count as independent news corroboration. Translated advisories are
marked as machine previews until a speaker reviews them. Broadcaster packs
use English until a language is reviewed.

Review pending reports with `GET /api/admin/reports` and a bearer `ADMIN_TOKEN`,
then `POST /api/admin/reports/{id}/review` with
`{"decision":"approved"}` or `{"decision":"rejected"}`.
