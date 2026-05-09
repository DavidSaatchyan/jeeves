from __future__ import annotations

import json
import time
from typing import Any

from ..config import get_settings

_settings = get_settings()
_use_redis = bool(_settings.redis_url)

if _use_redis:
    import redis.asyncio as aioredis
    _r: aioredis.Redis | None = aioredis.from_url(_settings.redis_url, decode_responses=True)
else:
    _r = None

_IN_MEMORY: dict[str, tuple[Any, float]] = {}
_DEFAULT_TTL = 86400


async def idempotency_get(key: str) -> Any | None:
    if _use_redis and _r is not None:
        raw = await _r.get(f"idempotent:{key}")
        if raw is not None:
            return json.loads(raw)
        return None
    entry = _IN_MEMORY.get(key)
    if entry and time.time() < entry[1]:
        return entry[0]
    _IN_MEMORY.pop(key, None)
    return None


async def idempotency_set(key: str, result: Any, ttl: int = _DEFAULT_TTL) -> None:
    if _use_redis and _r is not None:
        await _r.setex(f"idempotent:{key}", ttl, json.dumps(result, default=str))
    else:
        _IN_MEMORY[key] = (result, time.time() + ttl)


async def idempotency_check(key: str, result: Any, ttl: int = _DEFAULT_TTL) -> tuple[bool, Any | None]:
    existing = await idempotency_get(key)
    if existing is not None:
        return True, existing
    await idempotency_set(key, result, ttl)
    return False, None
