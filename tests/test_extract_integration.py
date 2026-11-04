"""Extraction + geocoding against real Postgres with faked LLM. Skips when unreachable.

Local: TEST_DATABASE_URL=postgresql+asyncpg://nino:nino@localhost:5433/nino_test
"""

import json
import os

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.llm import client as llm_client
from app.llm.client import LlmError
from app.llm.fake import get_fake
from app.repos import articles as articles_repo
from app.repos import events as events_repo
from app.repos import geonames as geonames_repo
from app.repos import regions as regions_repo
from app.repos.models import Base
from app.services import extract as extract_service
from app.services import geocode as geocode_service

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://nino:nino@localhost:5432/nino_test"
)


def test_country_to_iso():
    assert geocode_service.country_to_iso("Nigeria") == "NG"
    assert geocode_service.country_to_iso("viet nam") == "VN"
    assert geocode_service.country_to_iso("Perú") == "PE"
    assert geocode_service.country_to_iso("South Africa") == "ZA"
    assert geocode_service.country_to_iso("Atlantis") is None
    assert geocode_service.country_to_iso(None) is None


def test_extracted_event_must_be_inside_its_region():
    bbox = [-84, -20, -68, 5]
    assert extract_service.within_region(-12.1, -77.0, bbox)
    assert not extract_service.within_region(14.0, 121.0, bbox)


def test_parse_event_date():
    from datetime import date

    assert extract_service.parse_event_date("2026-10-28") == date(2026, 10, 28)
    assert extract_service.parse_event_date(None) is None
    assert extract_service.parse_event_date("last Sunday") is None


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
def fake_llm(monkeypatch):
    get_fake().reset()
    monkeypatch.setenv("LLM_EXTRACT", "fake:test")

    async def zero() -> float:
        return 0.0

    async def noop(**fields) -> None:
        return None

    monkeypatch.setattr(llm_client, "get_today_spend_usd", zero)
    monkeypatch.setattr(llm_client, "_record", noop)
    yield get_fake()
    get_fake().reset()


async def make_article(session, **overrides):
    await regions_repo.upsert_region(
        session,
        id="sahel-nigeria",
        name="Nigeria and the Sahel",
        risk="extreme",
        intensity=0.9,
        center_lat=12,
        center_lng=8,
        bbox=[-17, 2, 40, 24],
        config={},
    )
    fields = {
        "region_id": "sahel-nigeria",
        "url": "https://example.com/a1",
        "url_hash": "h1",
        "publisher": "Test",
        "language": "en",
        "title": "Heat in Kano",
        "excerpt": "Fourteen treated for heat exhaustion in Kano.",
        "content_hash": "c1",
    }
    fields.update(overrides)
    return await articles_repo.insert_article(session, **fields)


def extraction_json(**overrides) -> str:
    payload = {
        "is_relevant": True,
        "event_type": "heat_illness",
        "place": {"name": "Kano", "country": "Nigeria"},
        "event_date": "2026-10-28",
        "count": 14,
        "stated_cause": "heat",
        "evidence_quote": "treated for heat exhaustion in Kano",
        "language": "en",
        "confidence": 0.9,
    }
    payload.update(overrides)
    return json.dumps(payload)


async def test_extract_creates_placed_event(session_factory, fake_llm, monkeypatch):
    async def no_nominatim(place, country):
        raise AssertionError("local gazetteer should hit first")

    monkeypatch.setattr(geocode_service, "nominatim_lookup", no_nominatim)
    fake_llm.queue(extraction_json())
    async with session_factory() as session:
        await geonames_repo.upsert_seed(
            session, id=-1, name="Kano", asciiname="Kano", country="NG",
            lat=12.0, lng=8.52, population=100,
        )
        article = await make_article(session)
        event = await extract_service.extract_article(session, article.id)
        assert event is not None
        assert event.event_type == "heat_illness"
        assert event.lat == 12.0 and event.lng == 8.52
        assert event.count == 14
        refreshed = await session.get(type(article), article.id)
        assert refreshed.extracted_at is not None


async def test_extract_irrelevant_stores_nothing(session_factory, fake_llm):
    fake_llm.queue(json.dumps({"is_relevant": False}))
    async with session_factory() as session:
        article = await make_article(session)
        assert await extract_service.extract_article(session, article.id) is None
        refreshed = await session.get(type(article), article.id)
        assert refreshed.extracted_at is not None
        assert refreshed.extraction_error is None


async def test_extract_double_failure_marks_article(session_factory, fake_llm):
    fake_llm.queue("bad", "still bad")
    async with session_factory() as session:
        article = await make_article(session)
        assert await extract_service.extract_article(session, article.id) is None
        refreshed = await session.get(type(article), article.id)
        assert refreshed.extracted_at is not None
        assert refreshed.extraction_error is not None


async def test_extract_provider_error_leaves_pending(session_factory, fake_llm):
    # Empty fake queue -> provider failure -> LlmError, article stays pending.
    async with session_factory() as session:
        article = await make_article(session)
        with pytest.raises(LlmError):
            await extract_service.extract_article(session, article.id)
        refreshed = await session.get(type(article), article.id)
        assert refreshed.extracted_at is None


async def test_extract_skips_already_extracted(session_factory, fake_llm):
    fake_llm.queue(json.dumps({"is_relevant": False}))
    async with session_factory() as session:
        article = await make_article(session)
        await extract_service.extract_article(session, article.id)
        assert await extract_service.extract_article(session, article.id) is None
        assert len(fake_llm.calls) == 1


async def test_geocode_discards_unplaceable(session_factory, fake_llm, monkeypatch):
    async def no_result(place, country):
        return None

    monkeypatch.setattr(geocode_service, "nominatim_lookup", no_result)
    fake_llm.queue(extraction_json(place={"name": "Nowhere XYZ", "country": "Nigeria"}))
    async with session_factory() as session:
        article = await make_article(session)
        assert await extract_service.extract_article(session, article.id) is None


async def test_geocode_nominatim_fallback(session_factory, fake_llm, monkeypatch):
    async def fallback(place, country):
        return (1.5, 2.5)

    monkeypatch.setattr(geocode_service, "nominatim_lookup", fallback)
    fake_llm.queue(extraction_json(place={"name": "Smallville", "country": "Nigeria"}))
    async with session_factory() as session:
        article = await make_article(session)
        event = await extract_service.extract_article(session, article.id)
        assert event is not None
        assert (event.lat, event.lng) == (1.5, 2.5)


async def test_extract_pending_counts(session_factory, fake_llm, monkeypatch):
    async def no_nominatim(place, country):
        raise AssertionError("local gazetteer should hit first")

    monkeypatch.setattr(geocode_service, "nominatim_lookup", no_nominatim)
    fake_llm.queue(extraction_json(), json.dumps({"is_relevant": False}))
    async with session_factory() as session:
        await geonames_repo.upsert_seed(
            session, id=-1, name="Kano", asciiname="Kano", country="NG",
            lat=12.0, lng=8.52, population=100,
        )
        await make_article(session, url="https://example.com/a1", url_hash="h1")
        await make_article(session, url="https://example.com/a2", url_hash="h2", title="Sports")
        counts = await extract_service.extract_pending(session, "sahel-nigeria", 10)
        assert counts == {"processed": 2, "events": 1, "irrelevant": 1, "failed": 0}
        assert await events_repo.list_unclustered(session, "sahel-nigeria") != []
