"""Climate endpoint against real Postgres. Skips when unreachable.

Local: TEST_DATABASE_URL=postgresql+asyncpg://nino:nino@localhost:5433/nino_test
"""

import os

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.main import app
from app.repos import climate as climate_repo
from app.repos import regions as regions_repo
from app.repos.models import Base

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


@pytest.fixture
async def app_db(session_factory, monkeypatch):
    import app.core.db as db

    monkeypatch.setattr(db.settings, "database_url", TEST_DB_URL)
    monkeypatch.setattr(db, "_engine", None)
    yield session_factory
    monkeypatch.setattr(db, "_engine", None)


async def seed_region(session):
    await regions_repo.upsert_region(
        session, id="sahel-nigeria", name="Nigeria and the Sahel", risk="extreme",
        intensity=0.9, center_lat=12, center_lng=8, bbox=[-17, 2, 40, 24],
        config={"weather": {"baseline_start": 2015, "baseline_end": 2025}},
    )


async def test_climate_endpoint_shape(app_db):
    async with app_db() as session:
        await seed_region(session)
        await climate_repo.replace_region_cells(
            session, "sahel-nigeria",
            [
                {"region_id": "sahel-nigeria", "lat": 12.0, "lng": 8.0,
                 "temp_c": 41.0, "baseline_c": 36.0, "anomaly_c": 5.0},
                {"region_id": "sahel-nigeria", "lat": 13.0, "lng": 9.0,
                 "temp_c": 40.0, "baseline_c": None, "anomaly_c": None},
            ],
        )
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/regions/sahel-nigeria/climate")
    assert resp.status_code == 200
    body = resp.json()
    assert body["bbox"] == [-17, 2, 40, 24]
    assert body["cols"] == 24
    assert body["baselineYears"] == "2015-2025"
    assert body["generatedAt"] is not None
    assert len(body["cells"]) == 2
    assert body["cells"][0]["temp"] == 41.0
    assert body["cells"][0]["anomaly"] == 5.0


async def test_climate_empty_is_503(app_db):
    async with app_db() as session:
        await seed_region(session)
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/regions/sahel-nigeria/climate")
    assert resp.status_code == 503


async def test_climate_unknown_region_404(app_db):
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/regions/atlantis/climate")
    assert resp.status_code == 404
