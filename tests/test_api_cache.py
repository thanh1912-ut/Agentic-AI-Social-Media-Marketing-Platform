from __future__ import annotations

import asyncio

from redis.exceptions import ConnectionError as RedisConnectionError

from services.api.cache import cache_key, get_json_cache, set_json_cache


def test_cache_key_isolated_by_environment_workspace_and_query(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "staging")
    base = cache_key("dashboard", "workspace-a", "source=page-1")
    assert base.startswith("agentic:staging:v1:dashboard:workspace:workspace-a:")
    assert cache_key("dashboard", "workspace-b", "source=page-1") != base
    assert cache_key("dashboard", "workspace-a", "source=page-2") != base

    monkeypatch.setenv("APP_ENV", "production")
    assert cache_key("dashboard", "workspace-a", "source=page-1") != base


def test_optional_cache_serializes_json_with_ttl() -> None:
    class MemoryRedis:
        def __init__(self) -> None:
            self.value = None
            self.expiry = None

        async def set(self, key: str, value: str, ex: int) -> None:
            assert key == "cache-key"
            self.value = value
            self.expiry = ex

        async def get(self, key: str):
            assert key == "cache-key"
            return self.value

    redis = MemoryRedis()

    async def exercise() -> None:
        await set_json_cache(redis, "cache-key", {"ok": True}, 60)
        assert await get_json_cache(redis, "cache-key") == {"ok": True}

    asyncio.run(exercise())
    assert redis.expiry == 60


def test_optional_cache_fails_open_when_redis_is_unavailable() -> None:
    class BrokenRedis:
        async def get(self, _key: str):
            raise RedisConnectionError("down")

        async def set(self, _key: str, _value: str, ex: int) -> None:
            raise RedisConnectionError("down")

    async def exercise() -> None:
        redis = BrokenRedis()
        assert await get_json_cache(redis, "cache-key") is None
        await set_json_cache(redis, "cache-key", {"ok": True}, 60)
        assert await get_json_cache(None, "cache-key") is None

    asyncio.run(exercise())
