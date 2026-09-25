"""Best-effort tenant-scoped JSON cache for derived API responses."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError


logger = logging.getLogger(__name__)


def cache_key(namespace: str, company_id: str, signature: str) -> str:
    digest = hashlib.sha256(signature.encode("utf-8")).hexdigest()
    environment = os.getenv("APP_ENV", "development").strip().lower()
    return f"agentic:{environment}:v1:{namespace}:workspace:{company_id}:{digest}"


async def get_json_cache(client: Redis | None, key: str) -> Any | None:
    if client is None:
        return None
    try:
        value = await client.get(key)
        return json.loads(value) if value is not None else None
    except (RedisError, TypeError, ValueError):
        logger.info("optional response cache read failed")
        return None


async def set_json_cache(client: Redis | None, key: str, value: Any, ttl_seconds: int) -> None:
    if client is None:
        return
    try:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        await client.set(key, payload, ex=ttl_seconds)
    except (RedisError, TypeError, ValueError):
        logger.info("optional response cache write failed")
