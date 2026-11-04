import logging
import os
import time

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.core.config import settings
from app.core.db import get_session_factory
from app.llm import router
from app.llm.cache import LlmCache, get_default_cache
from app.llm.fake import echo_generate, get_fake
from app.llm.schemas import LlmParseError, parse_json
from app.repos import llm_calls as llm_call_repo

logger = logging.getLogger("ninowatch.llm")

ALLOWED_EFFORTS = ("low", "medium")

# USD per million tokens (input, output). Verify against current pricing.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "muse-spark": (1.25, 4.25),
    "default": (1.25, 4.25),
}


class LlmError(Exception):
    pass


class BudgetExceeded(LlmError):
    pass


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    price_in, price_out = MODEL_PRICING["default"]
    for prefix, prices in MODEL_PRICING.items():
        if prefix != "default" and model.startswith(prefix):
            price_in, price_out = prices
            break
    return (tokens_in * price_in + tokens_out * price_out) / 1_000_000


def make_client(base_url: str, api_key: str) -> AsyncOpenAI:
    return AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=60, max_retries=2)


def _provider_credentials(provider: str) -> tuple[str, str]:
    if provider == "meta":
        base_url = os.environ.get("MODEL_BASE_URL", settings.model_base_url)
        api_key = os.environ.get("MODEL_API_KEY", settings.model_api_key)
    elif provider == "openweights":
        base_url = os.environ.get("OPENWEIGHTS_BASE_URL", settings.openweights_base_url)
        api_key = os.environ.get("OPENWEIGHTS_API_KEY", settings.openweights_api_key)
    else:
        raise router.LlmConfigError(f"unknown provider {provider!r}")
    if not base_url or not api_key:
        raise router.LlmConfigError(f"missing base URL or API key for provider {provider!r}")
    return base_url, api_key


def get_client(provider: str) -> AsyncOpenAI:
    # Celery runs each task in a fresh event loop. A cached HTTP client can
    # retain connections bound to a loop that has already closed.
    base_url, api_key = _provider_credentials(provider)
    return make_client(base_url, api_key)


async def get_today_spend_usd() -> float:
    """Today's LLM spend; 0.0 when the database is unreachable (best effort)."""
    try:
        factory = get_session_factory()
        async with factory() as session:
            return await llm_call_repo.get_today_spend_usd(session)
    except Exception as e:
        logger.warning("spend lookup failed; assuming 0 (%s)", e)
        return 0.0


def _budget_usd() -> float:
    raw = os.environ.get("DAILY_LLM_BUDGET_USD")
    if raw is not None:
        try:
            return float(raw)
        except ValueError:
            pass
    return settings.daily_llm_budget_usd


async def _record(**fields) -> None:
    """Persist one llm_calls row. Never raises: observability must not break pipes."""
    try:
        factory = get_session_factory()
        async with factory() as session:
            await llm_call_repo.record_llm_call(session, **fields)
    except Exception as e:
        logger.warning("llm_calls logging failed (%s)", e)


async def _generate_openai(
    provider: str, model: str, system: str, user: str, effort: str, max_tokens: int
) -> tuple[str, int, int]:
    async with get_client(provider) as client:
        resp = await client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            reasoning={"effort": effort},
            max_output_tokens=max_tokens,
        )
    usage = getattr(resp, "usage", None)
    tokens_in = getattr(usage, "input_tokens", 0) or 0
    tokens_out = getattr(usage, "output_tokens", 0) or 0
    if not resp.output_text.strip():
        raise LlmError(
            f"model returned no text (status={resp.status}, output_tokens={tokens_out}, "
            f"max_output_tokens={max_tokens})"
        )
    return resp.output_text, tokens_in, tokens_out


async def complete(
    task: str, system: str, user: str, *, effort: str = "low", max_tokens: int = 2000
) -> str:
    """Run one LLM task; walks the route's fallback chain until one succeeds."""
    if effort not in ALLOWED_EFFORTS:
        raise ValueError(f"effort must be one of {ALLOWED_EFFORTS}, got {effort!r}")
    routes = router.resolve(task)
    spend = await get_today_spend_usd()
    if spend >= _budget_usd():
        raise BudgetExceeded(f"daily LLM budget exhausted (${spend:.2f} spent)")
    last_error: Exception | None = None
    for route in routes:
        started = time.perf_counter()
        try:
            if route.provider == "fake":
                result = await get_fake().generate(
                    model=route.model,
                    system=system,
                    user=user,
                    effort=effort,
                    max_tokens=max_tokens,
                )
                text, tokens_in, tokens_out = result.text, result.tokens_in, result.tokens_out
            elif route.provider == "echo":
                result = echo_generate(user=user, task=task)
                text, tokens_in, tokens_out = result.text, result.tokens_in, result.tokens_out
            elif route.provider in ("meta", "openweights"):
                text, tokens_in, tokens_out = await _generate_openai(
                    route.provider, route.model, system, user, effort, max_tokens
                )
            else:
                raise router.LlmConfigError(f"unknown provider {route.provider!r}")
        except Exception as e:
            last_error = e
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.warning("llm %s via %s failed: %s", task, route, e)
            await _record(
                task=task,
                provider=route.provider,
                model=route.model,
                latency_ms=latency_ms,
                error=f"{type(e).__name__}: {e}"[:2000],
            )
            continue
        latency_ms = int((time.perf_counter() - started) * 1000)
        if route.provider in ("fake", "echo"):
            cost = 0.0
        else:
            cost = estimate_cost(route.model, tokens_in, tokens_out)
        await _record(
            task=task,
            provider=route.provider,
            model=route.model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            cost_estimate=cost,
        )
        return text
    raise LlmError(f"all providers failed for task {task!r}: {last_error}")


async def complete_cached(
    task: str,
    system: str,
    user: str,
    *,
    prompt_version: str,
    effort: str = "low",
    max_tokens: int = 2000,
    cache: LlmCache | None = None,
) -> tuple[str, bool]:
    """Cached completion; returns (text, cache_hit). Required for advisories/translations."""
    from app.llm.cache import cache_key

    cache = cache or get_default_cache()
    model = router.resolve(task)[0].model
    key = cache_key(task, model, prompt_version, system + "\n" + user)
    hit = await cache.get(key)
    if hit is not None:
        await _record(
            task=task, provider="cache", model=model, cache_hit=True, error=None
        )
        return hit, True
    text = await complete(task, system, user, effort=effort, max_tokens=max_tokens)
    await cache.set(key, text)
    return text, False


async def complete_json_cached(
    task: str,
    system: str,
    user: str,
    model_cls: type[BaseModel],
    *,
    prompt_version: str,
    effort: str = "low",
    max_tokens: int = 2000,
    cache: LlmCache | None = None,
) -> tuple[BaseModel, bool]:
    """Cached JSON completion; returns (parsed, cache_hit)."""
    from app.llm.cache import cache_key

    store = cache or get_default_cache()
    model = router.resolve(task)[0].model
    key = cache_key(task, model, prompt_version, system + "\n" + user)
    hit = await store.get(key)
    if hit is not None:
        try:
            return parse_json(hit, model_cls), True
        except LlmParseError:
            pass  # poisoned entry falls through to regeneration
    parsed = await complete_json(
        task, system, user, model_cls,
        prompt_version=prompt_version, effort=effort, max_tokens=max_tokens,
    )
    await store.set(key, parsed.model_dump_json())
    return parsed, False


async def complete_json(
    task: str,
    system: str,
    user: str,
    model_cls: type[BaseModel],
    *,
    prompt_version: str = "v1",
    effort: str = "low",
    max_tokens: int = 2000,
) -> BaseModel:
    """Complete + validate; retries once with the validation error appended."""
    _ = prompt_version  # recorded by callers alongside outputs; part of the cache key there
    text = await complete(task, system, user, effort=effort, max_tokens=max_tokens)
    try:
        return parse_json(text, model_cls)
    except LlmParseError as first_error:
        retry_user = (
            f"{user}\n\nYour previous reply failed validation with this error:\n"
            f"{first_error}\nReply with corrected JSON only."
        )
        retry_text = await complete(task, system, retry_user, effort=effort, max_tokens=max_tokens)
        return parse_json(retry_text, model_cls)
