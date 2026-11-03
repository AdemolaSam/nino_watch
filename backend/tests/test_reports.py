import os

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.db import get_session
from app.main import app
from app.repos.models import Base, Region

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://nino:nino@localhost:5432/nino_test"
)


@pytest.fixture
async def report_db(monkeypatch):
    engine = create_async_engine(TEST_DB_URL)
    try:
        async with engine.connect():
            pass
    except Exception:
        await engine.dispose()
        pytest.skip("postgres unreachable; set TEST_DATABASE_URL")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(Region(
            id="sahel-nigeria", name="Nigeria and the Sahel", risk="extreme",
            intensity=0.9, center_lat=12, center_lng=8, bbox=[-17, 2, 40, 24], config={},
        ))
        await session.commit()

    async def test_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    monkeypatch.setattr(settings, "admin_token", "review-secret")
    yield
    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_report_review_and_public_visibility(report_db):
    payload = {
        "regionId": "sahel-nigeria", "kind": "heat", "placeName": "Kano",
        "description": "Several people needed help after working in the heat.",
    }
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post("/api/reports", json=payload)
        assert created.status_code == 201
        report_id = created.json()["id"]
        assert created.json()["status"] == "pending"
        assert (await client.get("/api/reports")).json() == []
        assert (await client.get("/api/admin/reports")).status_code == 401
        auth = {"Authorization": "Bearer review-secret"}
        pending = await client.get("/api/admin/reports", headers=auth)
        assert pending.json()[0]["id"] == report_id
        approved = await client.post(
            f"/api/admin/reports/{report_id}/review",
            headers=auth, json={"decision": "approved"},
        )
        assert approved.status_code == 200
        public = (await client.get("/api/reports?regionId=sahel-nigeria")).json()
        assert public[0]["status"] == "approved"
        assert public[0]["description"] == payload["description"]
        assert (await client.post(
            f"/api/admin/reports/{report_id}/review",
            headers=auth, json={"decision": "rejected"},
        )).status_code == 409
