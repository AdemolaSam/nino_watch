import httpx
import pytest
from httpx import ASGITransport

from app.main import app
from app.services.outlooks import load_outlooks


@pytest.mark.asyncio
async def test_outlooks_have_sources_and_dates():
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/outlooks")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 6
    assert {row["regionId"] for row in rows} == {row["region_id"] for row in load_outlooks()}
    assert all(row["sourceUrl"].startswith("https://") for row in rows)
    assert all(row["issuedAt"] <= row["validThrough"] for row in rows)
