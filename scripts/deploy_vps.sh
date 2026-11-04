#!/usr/bin/env bash
set -euo pipefail

deploy_sha="${1:?expected commit SHA}"
app_dir="$HOME/nino_watch"

if [[ ! -d "$app_dir/.git" ]]; then
  echo "Missing checkout at $app_dir; clone the repository there first." >&2
  exit 1
fi

cd "$app_dir"
git fetch --quiet origin main
git checkout --quiet --detach "$deploy_sha"

if [[ ! -f .env ]]; then
  echo "Missing $app_dir/.env; configure VPS secrets before deploying." >&2
  exit 1
fi
for key in MODEL_API_KEY ADMIN_TOKEN POSTGRES_PASSWORD DATABASE_URL CORS_ORIGINS; do
  if ! grep -Eq "^${key}=.+" .env; then
    echo "Missing $key in $app_dir/.env" >&2
    exit 1
  fi
done
if grep -Eq '^POSTGRES_PASSWORD=nino$' .env; then
  echo "Replace the example POSTGRES_PASSWORD before deploying." >&2
  exit 1
fi

docker compose up -d db redis
docker compose build api worker beat flower
docker compose run --rm api env PYTHONPATH=/srv alembic upgrade head
docker compose run --rm api python -m scripts.seed_regions
docker compose up -d --no-build

for attempt in {1..15}; do
  if health="$(curl -fsS http://127.0.0.1:8000/api/health)" && \
    [[ "$health" == *'"status":"ok"'* ]]; then
    echo "$health"
    echo "Deployment healthy at $deploy_sha"
    exit 0
  fi
  sleep 2
done

echo "Deployment failed health check" >&2
exit 1
