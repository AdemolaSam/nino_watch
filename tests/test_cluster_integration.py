"""Clustering orchestration against real Postgres. Skips when unreachable.

Local: TEST_DATABASE_URL=postgresql+asyncpg://nino:nino@localhost:5433/nino_test
"""

import os
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.repos import articles as articles_repo
from app.repos import clusters as clusters_repo
from app.repos import events as events_repo
from app.repos import regions as regions_repo
from app.repos.models import Base
from app.services import cluster as cluster_service

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


async def seed_region(session):
    await regions_repo.upsert_region(
        session, id="sahel-nigeria", name="N", risk="extreme", intensity=0.9,
        center_lat=12, center_lng=8, bbox=[0, 0, 0, 0], config={},
    )


async def add_event(session, key, **overrides):
    article = await articles_repo.insert_article(
        session, region_id="sahel-nigeria", url=f"https://example.com/{key}",
        url_hash=key, publisher=f"Outlet {key}", language="en", title=f"Title {key}",
        excerpt=f"Excerpt {key}", content_hash=key,
    )
    fields = {
        "article_id": article.id, "region_id": "sahel-nigeria",
        "event_type": "heat_illness", "place_name": "Kano", "country": "Nigeria",
        "lat": 12.0, "lng": 8.52, "event_date": date(2026, 10, 28),
    }
    fields.update(overrides)
    return await events_repo.create_event(session, **fields)


async def test_duplicates_collapse_to_one_cluster(session_factory):
    async with session_factory() as session:
        await seed_region(session)
        first = await add_event(session, "a1")
        second = await add_event(session, "a2", lat=12.03, lng=8.55,
                                 event_date=date(2026, 10, 29))
        counts = await cluster_service.cluster_events(session, "sahel-nigeria")
        assert counts == {"assigned": 2, "created": 1, "skipped": 0}
        clusters = await clusters_repo.list_region_clusters(session, "sahel-nigeria")
        assert len(clusters) == 1
        assert clusters[0].canonical_event_id == first.id
        refreshed = await events_repo.get_event(session, second.id)
        assert refreshed.cluster_id == clusters[0].id


async def test_far_and_mismatched_events_stay_separate(session_factory):
    async with session_factory() as session:
        await seed_region(session)
        await add_event(session, "a1")
        await add_event(session, "a2", lat=6.45, lng=3.39, place_name="Lagos")
        await add_event(session, "a3", event_type="flood")
        await add_event(session, "a4", event_date=date(2026, 9, 1))
        counts = await cluster_service.cluster_events(session, "sahel-nigeria")
        assert counts["created"] == 4
        assert counts["assigned"] == 4


async def test_null_dates_cluster_together_only(session_factory):
    async with session_factory() as session:
        await seed_region(session)
        await add_event(session, "a1", event_date=None)
        await add_event(session, "a2", event_date=None, lat=12.01, lng=8.53)
        await add_event(session, "a3", event_date=date(2026, 10, 28))
        counts = await cluster_service.cluster_events(session, "sahel-nigeria")
        assert counts["created"] == 2


async def test_rerun_is_idempotent(session_factory):
    async with session_factory() as session:
        await seed_region(session)
        await add_event(session, "a1")
        first = await cluster_service.cluster_events(session, "sahel-nigeria")
        second = await cluster_service.cluster_events(session, "sahel-nigeria")
        assert first["created"] == 1
        assert second == {"assigned": 0, "created": 0, "skipped": 0}


async def test_unplaced_events_skipped(session_factory):
    async with session_factory() as session:
        await seed_region(session)
        await add_event(session, "a1", lat=None, lng=None)
        counts = await cluster_service.cluster_events(session, "sahel-nigeria")
        assert counts == {"assigned": 0, "created": 0, "skipped": 1}
