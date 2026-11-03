from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repos.models import LlmCall


async def record_llm_call(
    session: AsyncSession,
    *,
    task: str,
    provider: str,
    model: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    latency_ms: int = 0,
    cache_hit: bool = False,
    cost_estimate: float = 0.0,
    error: str | None = None,
) -> LlmCall:
    call = LlmCall(
        task=task,
        provider=provider,
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
        cache_hit=cache_hit,
        cost_estimate=cost_estimate,
        error=error,
    )
    session.add(call)
    await session.commit()
    return call


async def get_today_spend_usd(session: AsyncSession) -> float:
    midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    result = await session.execute(
        select(func.coalesce(func.sum(LlmCall.cost_estimate), 0.0)).where(
            LlmCall.created_at >= midnight
        )
    )
    return float(result.scalar() or 0.0)
