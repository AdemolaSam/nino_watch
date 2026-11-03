"""Seed + regions/incidents endpoints against real Postgres. Skips when unreachable.

Uses a dedicated nino_test database (created once per postgres instance).
Local (compose stack): TEST_DATABASE_URL=postgresql+asyncpg://nino:nino@localhost:5433/nino_test
"""

import os
import sys
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import seed  # noqa: E402

from app.main import app  # noqa: E402
from app.repos.models import Base  # noqa: E402

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://nino:nino@localhost:5432/nino_test"
)


@pytest.fixture
async def seeded_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DB_URL)
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
    # Point the app's engine at the test DB.
    import app.core.db as db

    monkeypatch.setattr(db.settings, "database_url", TEST_DB_URL)
    monkeypatch.setattr(db, "_engine", None)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await seed.seed_regions(session)
        await seed.seed_incidents(session)
    yield factory
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
    monkeypatch.setattr(db, "_engine", None)


async def test_seed_is_idempotent(seeded_db):
    async with seeded_db() as session:
        assert await seed.seed_incidents(session) == 0


async def test_regions_end_to_end(seeded_db):
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/regions")
    assert resp.status_code == 200
    ids = sorted(r["id"] for r in resp.json())
    assert ids == [
        "andean-coast", "central-america", "east-africa", "sahel-nigeria",
        "southeast-asia", "southern-africa",
    ]
    sahel = next(r for r in resp.json() if r["id"] == "sahel-nigeria")
    assert sahel["risk"] == "extreme"
    assert {lang["code"] for lang in sahel["languages"]} >= {"en", "ha", "yo", "pcm", "id", "es"}


async def test_incidents_end_to_end(seeded_db):
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/incidents", params={"regionId": "sahel-nigeria"})
        assert resp.status_code == 200
        assert resp.json() == []
        empty = await client.get("/api/incidents", params={"regionId": "east-africa"})
        assert empty.status_code == 200
        assert empty.json() == []
        missing = await client.get("/api/incidents", params={"regionId": "atlantis"})
        assert missing.status_code == 404
