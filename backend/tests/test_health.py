import httpx
import pytest
from httpx import ASGITransport

from app.core import db
from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_health_ok(monkeypatch):
    async def ok() -> bool:
        return True

    async def no_ingest() -> None:
        return None

    monkeypatch.setattr(db, "check_db", ok)
    monkeypatch.setattr(db, "check_redis", ok)
    monkeypatch.setattr(db, "get_last_ingest_at", no_ingest)

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/health")

    assert resp.status_code == 200
    assert resp.json() == {
        "status": "ok",
        "db": "ok",
        "redis": "ok",
        "lastIngestAt": None,
    }


async def test_health_degraded_when_db_down(monkeypatch):
    async def fail() -> bool:
        return False

    async def ok() -> bool:
        return True

    async def no_ingest() -> None:
        return None

    monkeypatch.setattr(db, "check_db", fail)
    monkeypatch.setattr(db, "check_redis", ok)
    monkeypatch.setattr(db, "get_last_ingest_at", no_ingest)

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["db"] == "error"
    assert body["redis"] == "ok"
