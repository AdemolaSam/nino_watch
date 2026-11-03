import pytest

from app.llm import router
from app.llm.router import LlmConfigError, Route


def test_resolve_single(monkeypatch):
    monkeypatch.setenv("LLM_EXTRACT", "meta:muse-spark-1.3")
    assert router.resolve("extract") == [Route(provider="meta", model="muse-spark-1.3")]


def test_resolve_fallback_chain(monkeypatch):
    monkeypatch.setenv("LLM_EXTRACT", "openweights:muse-spark-open, meta:muse-spark-1.3")
    assert router.resolve("extract") == [
        Route(provider="openweights", model="muse-spark-open"),
        Route(provider="meta", model="muse-spark-1.3"),
    ]


def test_resolve_unknown_task():
    with pytest.raises(LlmConfigError):
        router.resolve("nope")


def test_resolve_bad_route_format(monkeypatch):
    monkeypatch.setenv("LLM_EXTRACT", "metause-spark")
    with pytest.raises(LlmConfigError):
        router.resolve("extract")


def test_resolve_empty(monkeypatch):
    monkeypatch.setenv("LLM_EXTRACT", "  ")
    with pytest.raises(LlmConfigError):
        router.resolve("extract")


def test_outlet_falls_back_to_advisory(monkeypatch):
    monkeypatch.delenv("LLM_OUTLET", raising=False)
    monkeypatch.setenv("LLM_ADVISORY", "meta:muse-spark-1.2")
    # settings default for llm_outlet is ""; env-first read sees no LLM_OUTLET
    import app.llm.router as r

    monkeypatch.setattr(r.settings, "llm_outlet", "")
    assert router.resolve("outlet") == [Route(provider="meta", model="muse-spark-1.2")]
