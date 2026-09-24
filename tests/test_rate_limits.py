"""Rate limit behavior and route wiring tests."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from redis.exceptions import RedisError

from services.api import rate_limits
from services.api.errors import ApiProblem


class FakeRedis:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.counts: dict[str, int] = {}
        self.error = error
        self.keys: list[str] = []

    async def eval(self, _script: str, _key_count: int, key: str, _window: int) -> int:
        if self.error:
            raise self.error
        self.keys.append(key)
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]


def _request(redis: FakeRedis | None = None) -> Request:
    app = FastAPI()
    app.state.rate_limiter = redis
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/test",
            "raw_path": b"/test",
            "query_string": b"",
            "headers": [],
            "client": ("203.0.113.9", 12345),
            "server": ("testserver", 80),
            "app": app,
        }
    )


def test_disabled_rate_limiter_does_not_require_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rate_limits, "settings", SimpleNamespace(rate_limits_enabled=False, app_env="development"))
    asyncio.run(rate_limits.rate_limit("test", max_requests=1, window_seconds=60)(_request()))


def test_limit_is_shared_by_scope_and_ip_and_rejects_request_over_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    redis = FakeRedis()
    monkeypatch.setattr(rate_limits, "settings", SimpleNamespace(rate_limits_enabled=True, app_env="development"))
    dependency = rate_limits.rate_limit("login", max_requests=2, window_seconds=900)

    asyncio.run(dependency(_request(redis)))
    asyncio.run(dependency(_request(redis)))
    with pytest.raises(ApiProblem) as raised:
        asyncio.run(dependency(_request(redis)))

    assert raised.value.status_code == 429
    assert raised.value.code == "rate_limited"
    assert raised.value.details == {"limit": 2, "window_seconds": 900}
    assert len(set(redis.keys)) == 1
    assert "203.0.113.9" not in redis.keys[0]


def test_redis_failure_fails_closed_in_production_and_open_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    redis = FakeRedis(error=RedisError("unavailable"))
    dependency = rate_limits.rate_limit("login", max_requests=2, window_seconds=900)

    monkeypatch.setattr(rate_limits, "settings", SimpleNamespace(rate_limits_enabled=True, app_env="production"))
    with pytest.raises(ApiProblem) as raised:
        asyncio.run(dependency(_request(redis)))
    assert raised.value.status_code == 503
    assert raised.value.code == "rate_limit_unavailable"

    monkeypatch.setattr(rate_limits, "settings", SimpleNamespace(rate_limits_enabled=True, app_env="development"))
    asyncio.run(dependency(_request(redis)))
