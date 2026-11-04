"""Seed regions (from config/regions/*.yaml) and sample incidents.

Idempotent: re-running changes nothing. All seeded incidents are labeled
"Sample data" in the API. Live pipeline rows (B3+) are never touched.

Usage: DATABASE_URL=... uv run python scripts/seed.py
"""

import asyncio
import hashlib
import sys
from datetime import UTC, date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.db import get_session_factory  # noqa: E402
from app.repos import regions as regions_repo  # noqa: E402
from app.repos.models import Article, Cluster, Event, Verification  # noqa: E402
from app.services.regions import load_all_region_configs  # noqa: E402

SEED_PUBLISHER = "NiñoWatch seed"

SEEDS = [
    {
        "region": "sahel-nigeria",
        "event_type": "heat_illness",
        "place": "Kano",
        "country": "Nigeria",
        "lat": 12.0,
        "lng": 8.5,
        "date": date(2026, 10, 28),
        "count": 14,
        "outlets": ["Seed Outlet A", "Seed Outlet B"],
        "status": "corroborated",
        "independent_outlets": 2,
        "official": False,
        "weather": True,
        "conflict": False,
    },
    {
        "region": "sahel-nigeria",
        "event_type": "heat_death",
        "place": "Niamey",
        "country": "Niger",
        "lat": 13.5,
        "lng": 2.1,
        "date": date(2026, 10, 25),
        "count": 3,
        "outlets": ["Seed Outlet A"],
        "status": "unverified",
        "independent_outlets": 1,
        "official": False,
        "weather": None,
        "conflict": False,
    },
    {
        "region": "sahel-nigeria",
        "event_type": "flood",
        "place": "Lagos",
        "country": "Nigeria",
        "lat": 6.5,
        "lng": 3.4,
        "date": date(2026, 10, 20),
        "count": None,
        "outlets": ["Seed Outlet A", "Seed Outlet B"],
        "status": "confirmed",
        "independent_outlets": 2,
        "official": True,
        "weather": True,
        "conflict": False,
    },
    {
        "region": "southeast-asia",
        "event_type": "heat_illness",
        "place": "Jakarta",
        "country": "Indonesia",
        "lat": -6.2,
        "lng": 106.8,
        "date": date(2026, 10, 27),
        "count": 22,
        "outlets": ["Seed Outlet A", "Seed Outlet C"],
        "status": "corroborated",
        "independent_outlets": 2,
        "official": False,
        "weather": True,
        "conflict": False,
    },
    {
        "region": "southeast-asia",
        "event_type": "heat_death",
        "place": "Manila",
        "country": "Philippines",
        "lat": 14.6,
        "lng": 121.0,
        "date": date(2026, 10, 22),
        "count": 5,
        "outlets": ["Seed Outlet A"],
        "status": "unverified",
        "independent_outlets": 1,
        "official": False,
        "weather": False,
        "conflict": True,
    },
]


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def seed_regions(session) -> int:
    count = 0
    for cfg in load_all_region_configs():
        await regions_repo.upsert_region(
            session,
            id=cfg.id,
            name=cfg.name,
            risk=cfg.risk,
            intensity=cfg.intensity,
            center_lat=cfg.center["lat"],
            center_lng=cfg.center["lng"],
            bbox=cfg.bbox,
            config=cfg.model_dump(),
        )
        count += 1
    return count


async def seed_incidents(session) -> int:
    count = 0
    for seed in SEEDS:
        place_key = seed["place"].lower()
        existing = await session.execute(
            select(Cluster).where(
                Cluster.region_id == seed["region"],
                Cluster.event_type == seed["event_type"],
                Cluster.place_key == place_key,
                Cluster.date_key == seed["date"],
            )
        )
        if existing.scalars().first() is not None:
            continue
        cluster = Cluster(
            region_id=seed["region"],
            event_type=seed["event_type"],
            place_key=place_key,
            date_key=seed["date"],
        )
        session.add(cluster)
        await session.flush()
        canonical_id = None
        for i, outlet in enumerate(seed["outlets"]):
            url = f"seed://{seed['region']}/{place_key}-{seed['date'].isoformat()}-{i}"
            article = Article(
                region_id=seed["region"],
                url=url,
                url_hash=sha256(url),
                publisher=SEED_PUBLISHER if i == 0 else outlet,
                ownership_group=None,
                language="en",
                title=f"Seed report: {seed['event_type']} in {seed['place']}",
                published_at=None,
                excerpt="Seeded sample excerpt, not a real article.",
                content_hash=sha256(url + "excerpt"),
                fetched_at=datetime.now(UTC),
            )
            session.add(article)
            await session.flush()
            event = Event(
                article_id=article.id,
                region_id=seed["region"],
                event_type=seed["event_type"],
                place_name=seed["place"],
                country=seed["country"],
                lat=seed["lat"],
                lng=seed["lng"],
                event_date=seed["date"],
                count=seed["count"],
                stated_cause=None,
                evidence_quote="Seeded sample quote.",
                extractor_model="seed",
                prompt_version="seed",
                confidence=1.0,
                cluster_id=cluster.id,
            )
            session.add(event)
            await session.flush()
            if canonical_id is None:
                canonical_id = event.id
        cluster.canonical_event_id = canonical_id
        session.add(
            Verification(
                cluster_id=cluster.id,
                status=seed["status"],
                independent_outlets=seed["independent_outlets"],
                official_match=seed["official"],
                weather_plausible=seed["weather"],
                conflict=seed["conflict"],
                evidence={"sample": True, "note": "Seeded demo data."},
                rule_version="seed",
            )
        )
        await session.commit()
        count += 1
    return count


async def main() -> None:
    factory = get_session_factory()
    async with factory() as session:
        n_regions = await seed_regions(session)
        n_incidents = await seed_incidents(session)
    print(f"seeded {n_regions} regions, {n_incidents} new incidents")


if __name__ == "__main__":
    asyncio.run(main())
