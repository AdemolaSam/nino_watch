import pytest

from app.llm import client
from app.llm.cache import LlmCache, cache_key
from app.llm.fake import get_fake
from app.llm.schemas import LlmParseError, TranslationResult


@pytest.fixture(autouse=True)
def clean_fake():
    get_fake().reset()
    yield
    get_fake().reset()


@pytest.fixture
def no_db(monkeypatch):
    async def zero() -> float:
        return 0.0

    async def noop(**fields) -> None:
        return None

    monkeypatch.setattr(client, "get_today_spend_usd", zero)
    monkeypatch.setattr(client, "_record", noop)


async def test_complete_fake_success(monkeypatch, no_db):
    monkeypatch.setenv("LLM_TRANSLATE", "fake:test-model")
    get_fake().queue('{"happening": "x"}')
    text = await client.complete("translate", "sys", "user")
    assert text == '{"happening": "x"}'
    assert len(get_fake().calls) == 1


async def test_complete_echo_needs_no_queue(monkeypatch, no_db):
    monkeypatch.setenv("LLM_TRANSLATE", "echo:m")
    text = await client.complete("translate", "sys", "user")
    assert "FAKE TRANSLATION" in text


async def test_complete_falls_through_to_second_route(monkeypatch, no_db):
    monkeypatch.setenv("LLM_TRANSLATE", "bogus:model, fake:test-model")
    get_fake().queue("fallback-text")
    text = await client.complete("translate", "sys", "user")
    assert text == "fallback-text"


async def test_complete_all_fail_raises(monkeypatch, no_db):
    monkeypatch.setenv("LLM_TRANSLATE", "bogus:model")
    with pytest.raises(client.LlmError):
        await client.complete("translate", "sys", "user")


async def test_complete_rejects_none_effort(monkeypatch, no_db):
    monkeypatch.setenv("LLM_TRANSLATE", "fake:m")
    with pytest.raises(ValueError):
        await client.complete("translate", "sys", "user", effort="none")


async def test_complete_json_retries_once_with_error(monkeypatch, no_db):
    monkeypatch.setenv("LLM_TRANSLATE", "fake:m")
    get_fake().queue("not json", '{"happening": "H", "atRisk": "R", "actions": "A"}')
    result = await client.complete_json("translate", "sys", "user", TranslationResult)
    assert isinstance(result, TranslationResult)
    assert result.happening == "H"
    assert len(get_fake().calls) == 2
    assert "validation" in get_fake().calls[1].user


async def test_complete_json_fails_after_second_failure(monkeypatch, no_db):
    monkeypatch.setenv("LLM_TRANSLATE", "fake:m")
    get_fake().queue("bad", "still bad")
    with pytest.raises(LlmParseError):
        await client.complete_json("translate", "sys", "user", TranslationResult)


async def test_budget_exceeded_blocks_call(monkeypatch):
    async def rich() -> float:
        return 999.0

    async def noop(**fields) -> None:
        return None

    monkeypatch.setattr(client, "get_today_spend_usd", rich)
    monkeypatch.setattr(client, "_record", noop)
    monkeypatch.setenv("LLM_TRANSLATE", "fake:m")
    monkeypatch.setenv("DAILY_LLM_BUDGET_USD", "10")
    get_fake().queue("x")
    with pytest.raises(client.BudgetExceeded):
        await client.complete("translate", "sys", "user")
    assert get_fake().queued == 1  # provider never called


def test_estimate_cost_spark():
    assert client.estimate_cost("muse-spark-1.3", 1_000_000, 1_000_000) == pytest.approx(5.50)


async def test_complete_json_cached_hit_and_poison(monkeypatch, no_db):
    monkeypatch.setenv("LLM_TRANSLATE", "fake:m")
    cache = LlmCache()
    get_fake().queue('{"happening": "H", "atRisk": "R", "actions": "A"}')
    first, hit1 = await client.complete_json_cached(
        "translate", "sys", "user", TranslationResult, prompt_version="v1", cache=cache
    )
    second, hit2 = await client.complete_json_cached(
        "translate", "sys", "user", TranslationResult, prompt_version="v1", cache=cache
    )
    assert (first.happening, hit1) == ("H", False)
    assert (second.happening, hit2) == ("H", True)
    assert len(get_fake().calls) == 1
    # Poisoned entry falls through to regeneration.
    from app.llm.cache import cache_key

    key = cache_key("translate", "m", "v1", "sys\nuser")
    await cache.set(key, "garbage{")
    get_fake().queue('{"happening": "H2", "atRisk": "R", "actions": "A"}')
    third, hit3 = await client.complete_json_cached(
        "translate", "sys", "user", TranslationResult, prompt_version="v1", cache=cache
    )
    assert (third.happening, hit3) == ("H2", False)


async def test_complete_cached_hits_cache(monkeypatch, no_db):
    monkeypatch.setenv("LLM_TRANSLATE", "fake:m")
    cache = LlmCache()
    get_fake().queue("fresh")
    first, hit1 = await client.complete_cached(
        "translate", "sys", "user", prompt_version="v1", cache=cache
    )
    second, hit2 = await client.complete_cached(
        "translate", "sys", "user", prompt_version="v1", cache=cache
    )
    assert (first, hit1) == ("fresh", False)
    assert (second, hit2) == ("fresh", True)
    assert len(get_fake().calls) == 1


def test_cache_key_stable_and_versioned():
    a = cache_key("t", "m", "v1", "input")
    assert a == cache_key("t", "m", "v1", "input")
    assert a != cache_key("t", "m", "v2", "input")
    assert a != cache_key("t", "m", "v1", "other")


async def test_memory_cache_roundtrip():
    cache = LlmCache()
    assert await cache.get("k") is None
    await cache.set("k", "v")
    assert await cache.get("k") == "v"
