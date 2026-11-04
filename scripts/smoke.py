"""End-to-end smoke: ingest-free pipeline on a scratch DB, asserts API outputs.

Pipeline: seed regions -> insert articles -> extract -> cluster -> verify ->
advisory -> pack, then GET every public endpoint and assert the contract.
LLM and weather are faked; Postgres must be real.

Runs ONLY against a database with "test" in its name (refuses anything else).

Usage: TEST_DATABASE_URL=... uv run python scripts/smoke.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://nino:nino@localhost:5432/nino_test"
)
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["LLM_EXTRACT"] = "fake:smoke"
os.environ["LLM_VERIFY_SIGNAL"] = "fake:smoke"
os.environ["LLM_ADVISORY"] = "fake:smoke"
os.environ["LLM_TRANSLATE"] = "fake:smoke"
os.environ["LLM_OUTLET"] = "fake:smoke"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from httpx import ASGITransport  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.llm import client as llm_client  # noqa: E402
from app.llm.cache import LlmCache  # noqa: E402
from app.llm.fake import get_fake  # noqa: E402
from app.main import app  # noqa: E402
from app.repos import articles as articles_repo  # noqa: E402
from app.repos.models import Base  # noqa: E402
from app.services import advisory as advisory_service  # noqa: E402
from app.services import cluster as cluster_service  # noqa: E402
from app.services import extract as extract_service  # noqa: E402
from app.services import outlet as outlet_service  # noqa: E402
from app.services import verify as verify_service  # noqa: E402
from app.services import weather as weather_service  # noqa: E402

WORDS_70 = " ".join(
    ["drink", "water", "rest", "shade", "check", "elders", "daily", "avoid", "noon", "heat"] * 7
)

CHECKS: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "ok" if condition else "FAIL"
    CHECKS.append(f"[{status}] {name}" + (f" ({detail})" if detail and not condition else ""))
    if not condition:
        raise SystemExit(f"SMOKE FAIL: {name} {detail}")


def extraction_json(place="Kano", country="Nigeria", day="2026-10-28") -> str:
    return json.dumps(
        {
            "is_relevant": True, "event_type": "heat_illness",
            "place": {"name": place, "country": country}, "event_date": day,
            "count": 14, "stated_cause": "heat",
            "evidence_quote": "treated for heat exhaustion", "language": "en",
            "confidence": 0.9,
        }
    )


async def main() -> None:
    if "test" not in TEST_DB_URL.rsplit("/", 1)[-1]:
        raise SystemExit("refusing to smoke-test a non-test database")

    async def zero() -> float:
        return 0.0

    async def noop(**fields) -> None:
        return None

    async def hot_day(event_type, lat, lng, day, region_weather, cache=None):
        return True, {"observed_max_c": 41.0}

    llm_client.get_today_spend_usd = zero  # type: ignore[method-assign]
    llm_client._record = noop  # type: ignore[method-assign]
    weather_service.plausibility_for = hot_day  # type: ignore[method-assign]

    engine = create_async_engine(TEST_DB_URL, pool_pre_ping=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    import seed

    get_fake().queue(
        extraction_json(),
        extraction_json(),
        json.dumps({"happening": "Hot week.", "atRisk": "Workers.", "actions": "Rest."}),
        json.dumps({"script": WORDS_70}),
        json.dumps({"sms": "Drink water and rest in shade today."}),
    )
    async with factory() as session:
        await seed.seed_regions(session)
        from app.repos import geonames as geonames_repo

        await geonames_repo.upsert_seed(
            session, id=-1, name="Kano", asciiname="Kano", country="NG",
            lat=12.0, lng=8.52, population=100,
        )
        headlines = [
            ("Heat wave strains Kano clinics", "Health workers treated dozens for heat illness"),
            ("Kano hospitals add night shifts", "Clinics opened extra wards as heat persisted"),
        ]
        for i, (title, excerpt) in enumerate(headlines):
            await articles_repo.insert_article(
                session, region_id="sahel-nigeria",
                url=f"https://smoke.example.com/heat-{i}", url_hash=f"smoke-{i}",
                publisher=f"Smoke Outlet {i}", ownership_group=f"smoke-{i}",
                language="en", title=title, excerpt=excerpt, content_hash=f"smoke-{i}",
            )
        counts = await extract_service.extract_pending(session, None, 10)
        check("extract yields 2 events", counts["events"] == 2, str(counts))
        clusters = await cluster_service.cluster_events(session, "sahel-nigeria")
        check("smoke events cluster", clusters["assigned"] == 2, str(clusters))
        verified = await verify_service.verify_pending(session, "sahel-nigeria", 10)
        check("clusters verified", verified["verified"] >= 1, str(verified))
        cache = LlmCache()
        english = await advisory_service.generate_english(session, "sahel-nigeria", cache)
        check("advisory generated", english is not None and english.version == 1)
        pack = await outlet_service.generate_pack(session, english.id)
        check("pack generated", pack is not None and pack.sms_segments == 1)

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        regions = (await client.get("/api/regions")).json()
        check("regions list", len(regions) == 6, str(len(regions)))
        outlooks = (await client.get("/api/outlooks")).json()
        check("outlooks list", len(outlooks) == 6, str(len(outlooks)))
        incidents = (
            await client.get("/api/incidents", params={"regionId": "sahel-nigeria"})
        ).json()
        live = incidents
        check("live incident present", len(live) == 1, str(len(live)))
        check("live incident corroborated", live[0]["status"] == "corroborated", live[0]["status"])
        advisory = (
            await client.get("/api/advisories/sahel-nigeria", params={"lang": "en"})
        ).json()
        check("advisory available", advisory["available"] is True)
        pack_body = (
            await client.get("/api/outlet-packs/sahel-nigeria", params={"lang": "en"})
        ).json()
        check("pack available", pack_body["available"] is True and pack_body["sms"] != "")
        health = (await client.get("/api/health")).json()
        check("health db ok", health["db"] == "ok", str(health))

    await engine.dispose()
    print("\n".join(CHECKS))
    print("SMOKE PASS")


if __name__ == "__main__":
    asyncio.run(main())
