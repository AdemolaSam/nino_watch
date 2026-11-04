import httpx
from httpx import ASGITransport

from app.main import app


async def test_404_shape(monkeypatch):
    from app.repos import regions as regions_repo

    async def no_region(session, region_id):
        return None

    monkeypatch.setattr(regions_repo, "get_region", no_region)
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/regions/atlantis")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "http_404"
    assert "atlantis" in body["error"]["message"]


async def test_422_shape_missing_query_param():
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/incidents")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


async def test_unknown_path_shape():
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "http_404"


async def test_cors_allows_configured_origin():
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/health", headers={"Origin": "http://localhost:3000"}
        )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


async def test_cors_blocks_unknown_origin():
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in resp.headers
