"""DB-backed LLM observability tests. Needs Postgres; skips when unreachable.

Local (compose stack): TEST_DATABASE_URL=postgresql+asyncpg://nino:nino@localhost:5433/nino
CI: postgres service on localhost:5432 (see .github/workflows/ci.yml).
"""

import os

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.repos import llm_calls as repo
from app.repos.models import Base, LlmCall

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
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def test_record_llm_call_persists(session_factory):
    async with session_factory() as session:
        call = await repo.record_llm_call(
            session,
            task="translate",
            provider="fake",
            model="m",
            tokens_in=10,
            tokens_out=20,
            latency_ms=5,
            cost_estimate=0.001,
        )
        assert isinstance(call, LlmCall)
        assert call.id is not None
        spend = await repo.get_today_spend_usd(session)
        assert spend == pytest.approx(0.001)
