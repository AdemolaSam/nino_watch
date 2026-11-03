import httpx
from httpx import ASGITransport

from app.api.schemas import IncidentResponse, RegionResponse
from app.main import app
from app.repos import regions as regions_repo
from app.services import incidents as incidents_service
from app.services import regions as regions_service

SAMPLE_REGION = RegionResponse(
    id="sahel-nigeria",
    name="Nigeria and the Sahel",
    names=["Nigeria and the Sahel"],
    bbox=[-17, 2, 40, 24],
    risk="extreme",
    lat=12,
    lng=8,
    intensity=0.95,
    heat=[],
    countries=None,
    languages=[{"code": "en", "label": "English"}, {"code": "ha", "label": "Hausa"}],
)

SAMPLE_INCIDENTS = [
    IncidentResponse(
        id="1",
        region_id="sahel-nigeria",
        lat=12.0,
        lng=8.5,
        title="[Sample] Heat illness reported in Kano on 2026-10-28",
        status="corroborated",
        evidence="Sample data; 2 independent outlets",
    )
]


async def test_list_regions_shape(monkeypatch):
    async def fake_list(session):
        return [SAMPLE_REGION]

    monkeypatch.setattr(regions_service, "list_region_responses", fake_list)
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/regions")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert body[0]["id"] == "sahel-nigeria"
    assert body[0]["bbox"] == [-17, 2, 40, 24]
    assert body[0]["languages"][1] == {"code": "ha", "label": "Hausa"}


async def test_get_region_shape(monkeypatch):
    async def fake_get(session, region_id):
        return SAMPLE_REGION if region_id == "sahel-nigeria" else None

    monkeypatch.setattr(regions_service, "get_region_response", fake_get)
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/regions/sahel-nigeria")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Nigeria and the Sahel"
        missing = await client.get("/api/regions/atlantis")
        assert missing.status_code == 404


async def test_list_incidents_shape(monkeypatch):
    async def fake_region(session, region_id):
        return object()

    async def fake_incidents(session, region_id):
        return SAMPLE_INCIDENTS

    monkeypatch.setattr(regions_repo, "get_region", fake_region)
    monkeypatch.setattr(incidents_service, "list_incident_responses", fake_incidents)
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/incidents", params={"regionId": "sahel-nigeria"})
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["regionId"] == "sahel-nigeria"
    assert body[0]["status"] == "corroborated"


async def test_list_incidents_unknown_region_404(monkeypatch):
    async def no_region(session, region_id):
        return None

    monkeypatch.setattr(regions_repo, "get_region", no_region)
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/incidents", params={"regionId": "atlantis"})
    assert resp.status_code == 404
