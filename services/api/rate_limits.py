"""Redis-backed, fail-closed production request limits for abuse-prone APIs."""

from __future__ import annotations

import hashlib
import logging

from fastapi import Request
from redis.exceptions import RedisError

from .config import settings
from .errors import ApiProblem


logger = logging.getLogger(__name__)

_INCREMENT_WITH_TTL = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


def rate_limit(scope: str, *, max_requests: int, window_seconds: int):
    if max_requests < 1 or window_seconds < 1:
        raise ValueError("rate limit values must be positive")

    async def dependency(request: Request) -> None:
        if not settings.rate_limits_enabled:
            return

        redis = getattr(request.app.state, "rate_limiter", None)
        if redis is None:
            raise ApiProblem(
                503,
                "rate_limit_unavailable",
                "Giới hạn an toàn hiện không khả dụng. Vui lòng thử lại sau.",
                retryable=True,
            )

        client_host = request.client.host if request.client else "unknown"
        client_key = hashlib.sha256(client_host.encode("utf-8")).hexdigest()
        key = f"agentic:rate:v1:{scope}:{client_key}"
        try:
            count = int(await redis.eval(_INCREMENT_WITH_TTL, 1, key, window_seconds))
        except RedisError as exc:
            if settings.app_env.casefold() in {"prod", "production"}:
                raise ApiProblem(
                    503,
                    "rate_limit_unavailable",
                    "Giới hạn an toàn hiện không khả dụng. Vui lòng thử lại sau.",
                    retryable=True,
                ) from exc
            logger.warning("rate limit store unavailable in development scope=%s", scope)
            return

        if count > max_requests:
            raise ApiProblem(
                429,
                "rate_limited",
                "Bạn đã thử quá nhiều lần. Vui lòng chờ rồi thử lại.",
                details={"limit": max_requests, "window_seconds": window_seconds},
                retryable=True,
            )

    dependency.__name__ = f"rate_limit_{scope}"
    return dependency
