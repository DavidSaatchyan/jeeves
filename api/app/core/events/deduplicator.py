from __future__ import annotations

from datetime import datetime, timedelta

from ...config import get_settings

_settings = get_settings()
_use_redis = bool(_settings.redis_url)

if _use_redis:
    import redis.asyncio as aioredis
    _r: aioredis.Redis | None = aioredis.from_url(_settings.redis_url, decode_responses=True)
else:
    _r = None

_IN_MEMORY_DEDUP: set[str] = set()
_DEDUP_TTL = 300


async def is_duplicate(event_id: str) -> bool:
    key = f"dedup:event:{event_id}"
    if _use_redis and _r is not None:
        exists = await _r.exists(key)
        if exists:
            return True
        await _r.setex(key, _DEDUP_TTL, "1")
        return False
    if event_id in _IN_MEMORY_DEDUP:
        return True
    _IN_MEMORY_DEDUP.add(event_id)
    if len(_IN_MEMORY_DEDUP) > 10000:
        _IN_MEMORY_DEDUP.clear()
    return False
