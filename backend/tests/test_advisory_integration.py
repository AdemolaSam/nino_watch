"""Advisory generation + translation + gating. Skips without Postgres.

Local: TEST_DATABASE_URL=postgresql+asyncpg://nino:nino@localhost:5433/nino_test
"""

import json
import os
from datetime import date

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.llm import client as llm_client
from app.llm.cache import LlmCache
from app.llm.fake import get_fake
from app.main import app
from app.repos import articles as articles_repo
from app.repos import clusters as clusters_repo
from app.repos import events as events_repo
from app.repos import regions as regions_repo
from app.repos import verifications as verifications_repo
from app.repos.models import Base
from app.services import advisory as advisory_service
from app.services import weather as weather_service

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://nino:nino@localhost:5432/nino_test"
)

ADVISORY_JSON = json.dumps({"happening": "Hot week.", "atRisk": "Workers.", "actions": "Rest."})
ADVISORY_JSON_V2 = json.dumps({"happening": "Hotter.", "atRisk": "All.", "actions": "Shade."})
TRANSLATION_JSON = json.dumps({"happening": "HA-Hot.", "atRisk": "HA-W.", "actions": "HA-R."})


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


@pytest.fixture
def fake_llm(monkeypatch):
    get_fake().reset()
    monkeypatch.setenv("LLM_ADVISORY", "fake:test")
    monkeypatch.setenv("LLM_TRANSLATE", "fake:test")

    async def zero() -> float:
        return 0.0

    async def noop(**fields) -> None:
        return None

    async def fixed_max(lat, lng, day, cache=None):
        return 41.0

    async def fixed_means(coords, month, day, start, end, cache=None):
        return {c: 36.0 for c in coords}

    monkeypatch.setattr(llm_client, "get_today_spend_usd", zero)
    monkeypatch.setattr(llm_client, "_record", noop)
    monkeypatch.setattr(weather_service, "daily_max_for", fixed_max)
    monkeypatch.setattr(weather_service, "baseline_means", fixed_means)
    yield get_fake()
    get_fake().reset()


async def seed_region(session, config=None):
    await regions_repo.upsert_region(
        session, id="sahel-nigeria", name="Nigeria and the Sahel", risk="extreme",
        intensity=0.9, center_lat=12, center_lng=8, bbox=[0, 0, 0, 0],
        config=config or {"languages": ["en", "ha"]},
    )


async def seed_verified_cluster(session):
    article = await articles_repo.insert_article(
        session, region_id="sahel-nigeria", url="https://example.com/v1",
        url_hash="v1", publisher="Outlet", language="en", title="Heat",
        excerpt="Heat in Kano", content_hash="v1",
    )
    event = await events_repo.create_event(
        session, article_id=article.id, region_id="sahel-nigeria",
        event_type="heat_illness", place_name="Kano", country="Nigeria",
        lat=12.0, lng=8.52, event_date=date(2026, 10, 28),
    )
    cluster = await clusters_repo.create_cluster(
        session, region_id="sahel-nigeria", event_type="heat_illness",
        place_key="kano", date_key=date(2026, 10, 28), canonical_event_id=event.id,
    )
    event.cluster_id = cluster.id
    await session.commit()
    await verifications_repo.upsert_verification(
        session, cluster.id, status="corroborated", independent_outlets=2,
        official_match=False, weather_plausible=True, conflict=False,
        evidence={}, rule_version="v1",
    )


async def test_facts_use_verified_only(app_db, fake_llm):
    async with app_db() as session:
        await seed_region(session)
        await seed_verified_cluster(session)
        facts, source_ids = await advisory_service.build_facts(session, "sahel-nigeria")
        assert "corroborated" in facts
        assert "Kano" in facts
        assert "41C" in facts
        assert len(source_ids) == 1


async def test_generate_english_dedupes_same_content(app_db, fake_llm):
    fake_llm.queue(ADVISORY_JSON, ADVISORY_JSON)
    cache = LlmCache()
    async with app_db() as session:
        await seed_region(session)
        first = await advisory_service.generate_english(session, "sahel-nigeria", cache)
        second = await advisory_service.generate_english(session, "sahel-nigeria", cache)
        assert first.version == 1
        assert second.id == first.id  # same hash, no new version
        assert len(fake_llm.calls) == 1  # second generation served from cache


async def test_generate_english_new_version_on_change(app_db, fake_llm):
    fake_llm.queue(ADVISORY_JSON, ADVISORY_JSON_V2)
    async with app_db() as session:
        await seed_region(session)
        # Distinct caches per call so the second call regenerates.
        first = await advisory_service.generate_english(session, "sahel-nigeria", LlmCache())
        second = await advisory_service.generate_english(session, "sahel-nigeria", LlmCache())
        assert (first.version, second.version) == (1, 2)


async def test_unknown_language_not_translated(app_db, fake_llm):
    fake_llm.queue(ADVISORY_JSON)
    async with app_db() as session:
        await seed_region(session)
        english = await advisory_service.generate_english(session, "sahel-nigeria", LlmCache())
        assert await advisory_service.translate_advisory(session, english, "xx") is None


async def test_translate_tested_language_cached(app_db, fake_llm, monkeypatch):
    fake_llm.queue(ADVISORY_JSON, TRANSLATION_JSON)
    cache = LlmCache()
    async with app_db() as session:
        await seed_region(session)
        english = await advisory_service.generate_english(session, "sahel-nigeria", cache)
        first = await advisory_service.translate_advisory(session, english, "ha", cache)
        assert first.happening == "HA-Hot."
        assert first.version == english.version
        calls_before = len(fake_llm.calls)
        second = await advisory_service.translate_advisory(session, english, "ha", cache)
        assert second.id == first.id
        assert len(fake_llm.calls) == calls_before  # row reuse, no new LLM call


async def test_advisory_api_available(app_db, fake_llm, monkeypatch):
    fake_llm.queue(ADVISORY_JSON, TRANSLATION_JSON)
    cache = LlmCache()
    async with app_db() as session:
        await seed_region(session)
        english = await advisory_service.generate_english(session, "sahel-nigeria", cache)
        await advisory_service.translate_advisory(session, english, "ha", cache)
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/advisories/sahel-nigeria", params={"lang": "ha"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is True
        assert body["lang"] == "ha"
        assert body["happening"] == "HA-Hot."
        assert body["atRisk"] == "HA-W."
        assert body["reviewStatus"] == "machine_preview"
        assert body["sourceEnglish"]["happening"] == "Hot week."


async def test_advisory_api_falls_back_to_english(app_db, fake_llm):
    fake_llm.queue(ADVISORY_JSON)
    async with app_db() as session:
        await seed_region(session)
        await advisory_service.generate_english(session, "sahel-nigeria", LlmCache())
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/advisories/sahel-nigeria", params={"lang": "ha"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is False
        assert body["happening"] == "Hot week."
        assert body["reviewStatus"] == "unavailable"
        missing = await client.get("/api/advisories/atlantis")
        assert missing.status_code == 404


async def test_advisory_api_503_when_missing(app_db):
    async with app_db() as session:
        await seed_region(session)
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/advisories/sahel-nigeria")
        assert resp.status_code == 503
