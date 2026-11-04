import logging
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        # Celery runs each task in a new event loop. A pooled asyncpg connection
        # cannot be reused by a later task's loop.
        _engine = create_async_engine(settings.database_url, poolclass=NullPool)
    return _engine


def get_session_factory() -> async_sessionmaker:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def check_db() -> bool:
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        logging.getLogger("ninowatch").warning("db check failed", exc_info=True)
        return False


async def check_redis() -> bool:
    import redis.asyncio as redis

    try:
        client = redis.from_url(settings.redis_url, socket_timeout=3)
        try:
            await client.ping()
        finally:
            await client.aclose()
        return True
    except Exception:
        logging.getLogger("ninowatch").warning("redis check failed", exc_info=True)
        return False


async def get_last_ingest_at() -> str | None:
    """ISO timestamp of the last successful ingest, or None. Wired up in B3."""
    import redis.asyncio as redis

    try:
        client = redis.from_url(settings.redis_url, socket_timeout=3)
        try:
            raw = await client.get("ninowatch:last_ingest_at")
        finally:
            await client.aclose()
        if raw is None:
            return None
        return raw.decode() if isinstance(raw, bytes) else str(raw)
    except Exception:
        return None
