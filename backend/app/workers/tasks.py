import asyncio
from datetime import UTC, datetime

from app.core.db import get_session_factory
from app.services.advisory import generate_all_regions, generate_region
from app.services.cluster import cluster_all_regions, cluster_events
from app.services.extract import extract_article, extract_pending
from app.services.geocode import geocode_event
from app.services.ingest import ingest_all_pilots, ingest_region
from app.services.outlet import generate_region_packs
from app.services.regions import load_all_region_configs, load_region_config
from app.services.verify import verify_cluster, verify_pending
from app.services.weather import refresh_region_grid
from app.workers.celery_app import celery_app


@celery_app.task(name="ninowatch.ping")
def ping() -> str:
    return "pong"


async def _set_last_ingest_at() -> None:
    import redis.asyncio as redis

    from app.core.config import settings

    try:
        client = redis.from_url(settings.redis_url, socket_timeout=3)
        try:
            await client.set("ninowatch:last_ingest_at", datetime.now(UTC).isoformat())
        finally:
            await client.aclose()
    except Exception:
        pass


@celery_app.task(name="ninowatch.ingest_region")
def ingest_region_task(region_id: str) -> int:
    async def run() -> int:
        factory = get_session_factory()
        async with factory() as session:
            total = await ingest_region(session, load_region_config(region_id))
        await _set_last_ingest_at()
        return total

    return asyncio.run(run())


@celery_app.task(name="ninowatch.ingest_all")
def ingest_all_task() -> dict[str, int]:
    async def run() -> dict[str, int]:
        factory = get_session_factory()
        async with factory() as session:
            results = await ingest_all_pilots(session)
        await _set_last_ingest_at()
        return results

    return asyncio.run(run())


@celery_app.task(name="ninowatch.extract_article")
def extract_article_task(article_id: int) -> int | None:
    async def run() -> int | None:
        factory = get_session_factory()
        async with factory() as session:
            event = await extract_article(session, article_id)
            return event.id if event else None

    return asyncio.run(run())


@celery_app.task(name="ninowatch.extract_pending_all")
def extract_pending_all_task(limit: int = 20) -> dict[str, int]:
    async def run() -> dict[str, int]:
        factory = get_session_factory()
        async with factory() as session:
            return await extract_pending(session, None, limit)

    return asyncio.run(run())


@celery_app.task(name="ninowatch.geocode_event")
def geocode_event_task(event_id: int) -> bool:
    async def run() -> bool:
        factory = get_session_factory()
        async with factory() as session:
            return await geocode_event(session, event_id)

    return asyncio.run(run())


@celery_app.task(name="ninowatch.cluster_region")
def cluster_region_task(region_id: str) -> dict[str, int]:
    async def run() -> dict[str, int]:
        factory = get_session_factory()
        async with factory() as session:
            return await cluster_events(session, region_id)

    return asyncio.run(run())


@celery_app.task(name="ninowatch.cluster_all")
def cluster_all_task() -> dict[str, dict[str, int]]:
    async def run() -> dict[str, dict[str, int]]:
        factory = get_session_factory()
        async with factory() as session:
            return await cluster_all_regions(session)

    return asyncio.run(run())


@celery_app.task(name="ninowatch.refresh_climate_region")
def refresh_climate_region_task(region_id: str) -> int:
    async def run() -> int:
        factory = get_session_factory()
        async with factory() as session:
            return await refresh_region_grid(session, region_id)

    return asyncio.run(run())


@celery_app.task(name="ninowatch.refresh_climate_all")
def refresh_climate_all_task() -> dict[str, int]:
    async def run() -> dict[str, int]:
        results = {}
        factory = get_session_factory()
        async with factory() as session:
            for region in load_all_region_configs():
                if region.pilot:
                    results[region.id] = await refresh_region_grid(session, region.id)
        return results

    return asyncio.run(run())


@celery_app.task(name="ninowatch.verify_cluster")
def verify_cluster_task(cluster_id: int) -> str | None:
    async def run() -> str | None:
        factory = get_session_factory()
        async with factory() as session:
            verification = await verify_cluster(session, cluster_id)
            return verification.status if verification else None

    return asyncio.run(run())


@celery_app.task(name="ninowatch.verify_pending_all")
def verify_pending_all_task(limit: int = 20) -> dict:
    async def run() -> dict:
        factory = get_session_factory()
        async with factory() as session:
            counts = await verify_pending(session, None, limit)
        for region_id in counts["refresh_regions"]:
            generate_advisory_task.delay(region_id)
        return counts

    return asyncio.run(run())


@celery_app.task(name="ninowatch.generate_advisory")
def generate_advisory_task(region_id: str) -> dict:
    async def run() -> dict:
        factory = get_session_factory()
        async with factory() as session:
            result = await generate_region(session, region_id)
        if result.get("version") is not None:
            generate_packs_task.delay(region_id)
        return result

    return asyncio.run(run())


@celery_app.task(name="ninowatch.generate_packs")
def generate_packs_task(region_id: str) -> dict[str, int]:
    async def run() -> dict[str, int]:
        factory = get_session_factory()
        async with factory() as session:
            return await generate_region_packs(session, region_id)

    return asyncio.run(run())


@celery_app.task(name="ninowatch.generate_advisories_all")
def generate_advisories_all_task() -> dict[str, dict]:
    async def run() -> dict[str, dict]:
        factory = get_session_factory()
        async with factory() as session:
            return await generate_all_regions(session)

    return asyncio.run(run())
