from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from ..config import get_settings

_settings = get_settings()
_use_redis = bool(_settings.redis_url)

if _use_redis:
    import redis.asyncio as aioredis
    _r: aioredis.Redis | None = aioredis.from_url(_settings.redis_url, decode_responses=True)
else:
    _r = None

_IN_MEMORY_LOCKS: dict[str, float] = {}
_IN_MEMORY_TTL = 30


async def acquire_lock(key: str, ttl: int = _IN_MEMORY_TTL) -> bool:
    if _use_redis and _r is not None:
        result = await _r.set(key, "1", nx=True, ex=ttl)
        return bool(result)
    now = time.time()
    expiry = _IN_MEMORY_LOCKS.get(key, 0)
    if now < expiry:
        return False
    _IN_MEMORY_LOCKS[key] = now + ttl
    return True


async def release_lock(key: str) -> None:
    if _use_redis and _r is not None:
        await _r.delete(key)
    else:
        _IN_MEMORY_LOCKS.pop(key, None)


async def refresh_lock(key: str, ttl: int = _IN_MEMORY_TTL) -> None:
    if _use_redis and _r is not None:
        await _r.expire(key, ttl)
    else:
        _IN_MEMORY_LOCKS[key] = time.time() + ttl


def lock_key_workflow(workflow_id: uuid.UUID) -> str:
    return f"lock:workflow:{workflow_id}"


def lock_key_entity(entity_type: str, entity_id: str) -> str:
    return f"lock:entity:{entity_type}:{entity_id}"


def lock_key_subscription(subscription_id: str) -> str:
    return lock_key_entity("subscription", subscription_id)


def lock_key_invoice(invoice_id: str) -> str:
    return lock_key_entity("invoice", invoice_id)


@asynccontextmanager
async def workflow_lock(workflow_id: uuid.UUID) -> AsyncIterator[bool]:
    key = lock_key_workflow(workflow_id)
    acquired = await acquire_lock(key)
    try:
        yield acquired
    finally:
        if acquired:
            await release_lock(key)
