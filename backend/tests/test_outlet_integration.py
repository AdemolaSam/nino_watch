"""Broadcaster packs against real Postgres with faked LLM. Skips when unreachable.

Local: TEST_DATABASE_URL=postgresql+asyncpg://nino:nino@localhost:5433/nino_test
"""

import json
import os

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.llm import client as llm_client
from app.llm.fake import get_fake
from app.main import app
from app.repos import advisories as advisories_repo
from app.repos import regions as regions_repo
from app.repos.models import Base
from app.services import outlet as outlet_service

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://nino:nino@localhost:5432/nino_test"
)

WORDS_70 = " ".join(
    ["drink", "water", "rest", "shade", "check", "elders", "daily", "avoid", "noon", "heat"] * 7
)
assert len(WORDS_70.split()) == 70


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
    monkeypatch.setenv("LLM_OUTLET", "fake:test")

    async def zero() -> float:
        return 0.0

    async def noop(**fields) -> None:
        return None

    monkeypatch.setattr(llm_client, "get_today_spend_usd", zero)
    monkeypatch.setattr(llm_client, "_record", noop)
    yield get_fake()
    get_fake().reset()


async def seed_advisory(session, lang="en", version=1):
    await regions_repo.upsert_region(
        session, id="sahel-nigeria", name="N", risk="extreme", intensity=0.9,
        center_lat=12, center_lng=8, bbox=[0, 0, 0, 0], config={"languages": ["en"]},
    )
    return await advisories_repo.create_advisory(
        session, region_id="sahel-nigeria", lang=lang, version=version,
        content_hash=f"h{lang}{version}", happening="Hot.", at_risk="Workers.",
        actions="Rest.", source_cluster_ids=[], model="m", prompt_version="v1",
    )


async def test_pack_happy_path(app_db, fake_llm):
    fake_llm.queue(
        json.dumps({"script": WORDS_70}),
        json.dumps({"sms": "Drink water and rest in shade today."}),
    )
    async with app_db() as session:
        advisory = await seed_advisory(session)
        pack = await outlet_service.generate_pack(session, advisory.id)
        assert pack is not None
        assert pack.sms_segments == 1
        assert pack.lang == "en"
        # Idempotent re-run returns the same row without new LLM calls.
        again = await outlet_service.generate_pack(session, advisory.id)
        assert again.id == pack.id
        assert len(fake_llm.calls) == 2


async def test_pack_retries_invalid_radio(app_db, fake_llm):
    fake_llm.queue(
        json.dumps({"script": "Too short."}),
        json.dumps({"script": WORDS_70}),
        json.dumps({"sms": "Drink water."}),
    )
    async with app_db() as session:
        advisory = await seed_advisory(session)
        pack = await outlet_service.generate_pack(session, advisory.id)
        assert pack is not None
        assert "validation" in fake_llm.calls[1].user


async def test_pack_rejects_persistent_bad_radio(app_db, fake_llm):
    fake_llm.queue(json.dumps({"script": "Too short."}), json.dumps({"script": "Short."}))
    async with app_db() as session:
        advisory = await seed_advisory(session)
        assert await outlet_service.generate_pack(session, advisory.id) is None


async def test_pack_retries_long_sms(app_db, fake_llm):
    fake_llm.queue(
        json.dumps({"script": WORDS_70}),
        json.dumps({"sms": "x" * 400}),
        json.dumps({"sms": "Drink water and rest."}),
    )
    async with app_db() as session:
        advisory = await seed_advisory(session)
        pack = await outlet_service.generate_pack(session, advisory.id)
        assert pack is not None
        assert pack.sms == "Drink water and rest."


async def test_pack_api_available(app_db, fake_llm):
    fake_llm.queue(
        json.dumps({"script": WORDS_70}),
        json.dumps({"sms": "Drink water and rest in shade today."}),
    )
    async with app_db() as session:
        advisory = await seed_advisory(session)
        await outlet_service.generate_pack(session, advisory.id)
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/outlet-packs/sahel-nigeria")
        assert resp.status_code == 200
        body = resp.json()
        assert body["available"] is True
        assert body["radioScript"].startswith("drink water")
        assert body["sms"].startswith("Drink water")
        missing = await client.get("/api/outlet-packs/atlantis")
        assert missing.status_code == 404


async def test_pack_api_falls_back_to_english(app_db, fake_llm):
    fake_llm.queue(
        json.dumps({"script": WORDS_70}),
        json.dumps({"sms": "Drink water."}),
    )
    async with app_db() as session:
        advisory = await seed_advisory(session)
        await outlet_service.generate_pack(session, advisory.id)
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/outlet-packs/sahel-nigeria", params={"lang": "ha"})
        assert resp.status_code == 200
        assert resp.json()["available"] is False
        assert resp.json()["sms"] == "Drink water."


async def test_pack_api_503_without_pack(app_db):
    async with app_db() as session:
        await seed_advisory(session)
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/outlet-packs/sahel-nigeria")
        assert resp.status_code == 503
