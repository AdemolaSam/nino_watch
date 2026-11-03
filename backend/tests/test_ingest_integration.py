"""Ingest against real Postgres with faked HTTP. Skips when unreachable.

Local: TEST_DATABASE_URL=postgresql+asyncpg://nino:nino@localhost:5433/nino_test
"""

import os

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.repos.models import Base
from app.services import ingest as ingest_service
from app.services.regions import RegionConfig
from tests.test_ingest import SAMPLE_RSS

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://nino:nino@localhost:5432/nino_test"
)


@pytest.fixture
async def session_factory():
    engine = create_async_engine(TEST_DB_URL, pool_pre_ping=True)
    try:
        async with engine.connect():
            pass
    except Exception:
        await engine.dispose()
        pytest.skip("postgres unreachable; set TEST_DATABASE_URL")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def make_region(**overrides) -> RegionConfig:
    data = {
        "id": "sahel-nigeria",
        "name": "Nigeria and the Sahel",
        "news_sources": [
            {
                "name": "Test Outlet",
                "url": "https://example.com/feed",
                "language": "en",
                "ownership_group": "test-group",
            }
        ],
        "official_sources": [],
    }
    data.update(overrides)
    return RegionConfig.model_validate(data)


async def test_ingest_stores_and_dedupes(session_factory, monkeypatch):
    async def fake_fetch(url: str) -> bytes:
        if url.endswith("/robots.txt"):
            raise RuntimeError("no robots here")
        return SAMPLE_RSS

    async def allowed(url: str) -> bool:
        return True

    monkeypatch.setattr(ingest_service, "fetch_url", fake_fetch)
    monkeypatch.setattr(ingest_service, "robots_allowed", allowed)
    region = make_region()
    async with session_factory() as session:
        # Region row must exist for the FK.
        from app.repos import regions as regions_repo

        await regions_repo.upsert_region(
            session,
            id=region.id,
            name=region.name,
            risk="extreme",
            intensity=0.9,
            center_lat=12,
            center_lng=8,
            bbox=[-17, 2, 40, 24],
            config={},
        )
        first = await ingest_service.ingest_source(session, region, region.news_sources[0])
        assert first == 1
        second = await ingest_service.ingest_source(session, region, region.news_sources[0])
        assert second == 0


async def test_ingest_respects_robots(session_factory, monkeypatch):
    async def denied(url: str) -> bool:
        return False

    async def exploding_fetch(url: str) -> bytes:
        raise AssertionError("must not fetch when robots disallow")

    monkeypatch.setattr(ingest_service, "robots_allowed", denied)
    monkeypatch.setattr(ingest_service, "fetch_url", exploding_fetch)
    region = make_region()
    async with session_factory() as session:
        stored = await ingest_service.ingest_source(session, region, region.news_sources[0])
        assert stored == 0


async def test_ingest_fetch_failure_stores_nothing(session_factory, monkeypatch):
    async def allowed(url: str) -> bool:
        return True

    async def failing_fetch(url: str) -> bytes:
        raise RuntimeError("connection reset")

    monkeypatch.setattr(ingest_service, "robots_allowed", allowed)
    monkeypatch.setattr(ingest_service, "fetch_url", failing_fetch)
    region = make_region()
    async with session_factory() as session:
        stored = await ingest_service.ingest_source(session, region, region.news_sources[0])
        assert stored == 0
