"""Verification engine against real Postgres with faked LLM. Skips when unreachable.

Local: TEST_DATABASE_URL=postgresql+asyncpg://nino:nino@localhost:5433/nino_test
"""

import json
import os
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.llm import client as llm_client
from app.llm.fake import get_fake
from app.repos import articles as articles_repo
from app.repos import clusters as clusters_repo
from app.repos import events as events_repo
from app.repos import regions as regions_repo
from app.repos import verifications as verifications_repo
from app.repos.models import Base
from app.services import cluster as cluster_service
from app.services import verify as verify_service
from app.services import weather as weather_service

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
def fake_llm(monkeypatch):
    get_fake().reset()
    monkeypatch.setenv("LLM_VERIFY_SIGNAL", "fake:test")

    async def zero() -> float:
        return 0.0

    async def noop(**fields) -> None:
        return None

    monkeypatch.setattr(llm_client, "get_today_spend_usd", zero)
    monkeypatch.setattr(llm_client, "_record", noop)
    yield get_fake()
    get_fake().reset()


@pytest.fixture
def hot_weather(monkeypatch):
    async def plausible(event_type, lat, lng, day, region_weather, cache=None):
        return True, {"observed_max_c": 41.0}

    monkeypatch.setattr(weather_service, "plausibility_for", plausible)


async def seed_region(session):
    await regions_repo.upsert_region(
        session, id="sahel-nigeria", name="N", risk="extreme", intensity=0.9,
        center_lat=12, center_lng=8, bbox=[0, 0, 0, 0], config={},
    )


async def add_cluster(session, key, outlets=("Outlet A", "Outlet B"), official=None):
    """Cluster with one event per outlet + optional official article."""
    cluster = await clusters_repo.create_cluster(
        session, region_id="sahel-nigeria", event_type="heat_illness",
        place_key="kano", date_key=date(2026, 10, 28),
    )
    canonical_id = None
    for i, outlet in enumerate(outlets):
        article = await articles_repo.insert_article(
            session, region_id="sahel-nigeria", url=f"https://example.com/{key}-{i}",
            url_hash=f"{key}-{i}", publisher=outlet, language="en",
            title=f"Heat in Kano {i}", excerpt=f"Clinics busy in Kano {i}",
            content_hash=f"{key}-{i}",
        )
        event = await events_repo.create_event(
            session, article_id=article.id, region_id="sahel-nigeria",
            event_type="heat_illness", place_name="Kano", country="Nigeria",
            lat=12.0, lng=8.52, event_date=date(2026, 10, 28), count=14,
            cluster_id=cluster.id,
        )
        if canonical_id is None:
            canonical_id = event.id
    if official is not None:
        await articles_repo.insert_article(
            session, region_id="sahel-nigeria", url=f"https://example.com/{key}-off",
            url_hash=f"{key}-off", publisher=official, ownership_group="official",
            language="en", title="Ministry bulletin", excerpt="Ministry confirms cases",
            published_at=datetime(2026, 10, 28, tzinfo=UTC), content_hash=f"{key}-off",
        )
    cluster.canonical_event_id = canonical_id
    await session.commit()
    return cluster


async def test_two_outlets_corroborated(session_factory, fake_llm, hot_weather):
    async with session_factory() as session:
        await seed_region(session)
        cluster = await add_cluster(session, "c1")
        verification = await verify_service.verify_cluster(session, cluster.id)
        assert verification.status == "corroborated"
        assert verification.independent_outlets == 2
        assert verification.weather_plausible is True
        assert verification.conflict is False
        assert verification.rule_version == "v1"
        assert len(verification.evidence["articles"]) == 2


async def test_official_match_confirmed(session_factory, fake_llm, hot_weather):
    fake_llm.queue(json.dumps({"stance": "match", "reason": "ministry confirms"}))
    async with session_factory() as session:
        await seed_region(session)
        cluster = await add_cluster(session, "c1", outlets=("Outlet A",), official="MOH")
        verification = await verify_service.verify_cluster(session, cluster.id)
        assert verification.status == "confirmed"
        assert verification.official_match is True


async def test_official_contradict_conflicts(session_factory, fake_llm, hot_weather):
    fake_llm.queue(json.dumps({"stance": "contradict", "reason": "ministry denies"}))
    async with session_factory() as session:
        await seed_region(session)
        cluster = await add_cluster(session, "c1", official="MOH")
        verification = await verify_service.verify_cluster(session, cluster.id)
        assert verification.status == "unverified"
        assert verification.conflict is True


async def test_implausible_weather_conflicts(session_factory, fake_llm, monkeypatch):
    async def implausible(event_type, lat, lng, day, region_weather, cache=None):
        return False, {"observed_max_c": 22.0}

    monkeypatch.setattr(weather_service, "plausibility_for", implausible)
    async with session_factory() as session:
        await seed_region(session)
        cluster = await add_cluster(session, "c1")
        verification = await verify_service.verify_cluster(session, cluster.id)
        assert verification.status == "unverified"
        assert verification.conflict is True


async def test_single_source_unverified(session_factory, fake_llm, hot_weather):
    async with session_factory() as session:
        await seed_region(session)
        cluster = await add_cluster(session, "c1", outlets=("Outlet A",))
        verification = await verify_service.verify_cluster(session, cluster.id)
        assert verification.status == "unverified"
        assert verification.conflict is False


async def test_reverify_upserts_same_row(session_factory, fake_llm, hot_weather):
    async with session_factory() as session:
        await seed_region(session)
        cluster = await add_cluster(session, "c1")
        first = await verify_service.verify_cluster(session, cluster.id)
        second = await verify_service.verify_cluster(session, cluster.id)
        assert first.id == second.id
        assert second.status == "corroborated"


async def test_verify_pending_only_unverified(session_factory, fake_llm, hot_weather):
    async with session_factory() as session:
        await seed_region(session)
        cluster = await add_cluster(session, "c1")
        await add_cluster(session, "c2", outlets=("Outlet A",))
        await verify_service.verify_cluster(session, cluster.id)
        counts = await verify_service.verify_pending(session, "sahel-nigeria", 10)
        assert counts["verified"] == 1
        assert counts["failed"] == 0
        assert counts["refresh_regions"] == []


async def test_merge_same_events(session_factory, fake_llm):
    fake_llm.queue(json.dumps({"match": True, "reason": "same Kano outbreak"}))
    async with session_factory() as session:
        await seed_region(session)
        first = await add_cluster(session, "c1", outlets=("Outlet A",))
        second = await add_cluster(session, "c2", outlets=("Outlet B",))
        # Push the second cluster just outside the deterministic window (>50km).
        for event in await verifications_repo.list_cluster_events(session, second.id):
            event.lat, event.lng = 12.6, 8.52
        await session.commit()
        merged = await cluster_service.merge_same_events(session, "sahel-nigeria")
        assert merged == 1
        remaining = await clusters_repo.list_region_clusters(session, "sahel-nigeria")
        assert [c.id for c in remaining] == [first.id]
        moved = await verifications_repo.list_cluster_events(session, first.id)
        assert len(moved) == 2


async def test_merge_rejects_different_events(session_factory, fake_llm):
    fake_llm.queue(json.dumps({"match": False, "reason": "different cities"}))
    async with session_factory() as session:
        await seed_region(session)
        await add_cluster(session, "c1", outlets=("Outlet A",))
        second = await add_cluster(session, "c2", outlets=("Outlet B",))
        for event in await verifications_repo.list_cluster_events(session, second.id):
            event.lat, event.lng = 12.6, 8.52
        await session.commit()
        assert await cluster_service.merge_same_events(session, "sahel-nigeria") == 0
        remaining = await clusters_repo.list_region_clusters(session, "sahel-nigeria")
        assert len(remaining) == 2


async def test_merge_provider_error_stops_gracefully(session_factory, fake_llm):
    # Empty queue -> provider failure -> 0 merges, clusters untouched.
    async with session_factory() as session:
        await seed_region(session)
        await add_cluster(session, "c1", outlets=("Outlet A",))
        second = await add_cluster(session, "c2", outlets=("Outlet B",))
        for event in await verifications_repo.list_cluster_events(session, second.id):
            event.lat, event.lng = 12.6, 8.52
        await session.commit()
        assert await cluster_service.merge_same_events(session, "sahel-nigeria") == 0
