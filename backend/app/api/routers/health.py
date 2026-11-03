from datetime import datetime

from fastapi import APIRouter

from app.api.schemas import HealthResponse
from app.core import db

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    db_ok = await db.check_db()
    redis_ok = await db.check_redis()
    raw = await db.get_last_ingest_at()
    last_ingest_at = datetime.fromisoformat(raw) if raw else None
    status = "ok" if db_ok and redis_ok else "degraded"
    return HealthResponse(
        status=status,
        db="ok" if db_ok else "error",
        redis="ok" if redis_ok else "error",
        last_ingest_at=last_ingest_at,
    )
