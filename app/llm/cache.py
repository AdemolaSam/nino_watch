import hashlib

DEFAULT_TTL_SECONDS = 7 * 24 * 3600


def cache_key(task: str, model: str, prompt_version: str, input_text: str) -> str:
    digest = hashlib.sha256(
        "\x00".join([task, model, prompt_version, input_text]).encode("utf-8")
    ).hexdigest()
    return f"llm:{digest}"


class LlmCache:
    """Redis-backed cache with a process-local memory fallback.

    Pass ``redis_url=None`` for a pure in-memory cache (tests, scripts).
    Redis failures fall back to memory rather than failing the caller.
    """

    def __init__(self, redis_url: str | None = None) -> None:
        self._redis_url = redis_url
        self._memory: dict[str, str] = {}
        self._redis = None

    async def _redis_client(self):
        if self._redis is None and self._redis_url:
            import redis.asyncio as redis

            self._redis = redis.from_url(self._redis_url, socket_timeout=3)
        return self._redis

    async def get(self, key: str) -> str | None:
        if key in self._memory:
            return self._memory[key]
        client = await self._redis_client()
        if client is None:
            return None
        try:
            raw = await client.get(key)
        except Exception:
            return self._memory.get(key)
        if raw is None:
            return None
        value = raw.decode() if isinstance(raw, bytes) else str(raw)
        self._memory[key] = value
        return value

    async def set(self, key: str, value: str, ttl: int = DEFAULT_TTL_SECONDS) -> None:
        self._memory[key] = value
        client = await self._redis_client()
        if client is None:
            return
        try:
            await client.set(key, value, ex=ttl)
        except Exception:
            pass

    async def close(self) -> None:
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:
                pass
            self._redis = None


_default_cache: LlmCache | None = None


def get_default_cache() -> LlmCache:
    global _default_cache
    if _default_cache is None:
        import os

        from app.core.config import settings

        if os.environ.get("LLM_CACHE", "").lower() in ("none", "memory", "off"):
            _default_cache = LlmCache()
        else:
            _default_cache = LlmCache(
                redis_url=os.environ.get("LLM_CACHE_URL", settings.redis_url)
            )
    return _default_cache
