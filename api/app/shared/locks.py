from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import AsyncIterator

from ..config import get_settings


class LockManager(ABC):
    """Abstract interface for distributed lock backends."""

    @abstractmethod
    async def acquire_lock(self, key: str, ttl: int) -> bool:
        ...

    @abstractmethod
    async def release_lock(self, key: str) -> None:
        ...

    @abstractmethod
    async def refresh_lock(self, key: str, ttl: int) -> None:
        ...


class _InMemoryLockManager(LockManager):
    """In-memory lock backend for dev/single-process."""

    def __init__(self) -> None:
        self._locks: dict[str, float] = {}
        self._default_ttl = 30

    async def acquire_lock(self, key: str, ttl: int | None = None) -> bool:
        ttl = ttl or self._default_ttl
        now = time.time()
        expiry = self._locks.get(key, 0)
        if now < expiry:
            return False
        self._locks[key] = now + ttl
        return True

    async def release_lock(self, key: str) -> None:
        self._locks.pop(key, None)

    async def refresh_lock(self, key: str, ttl: int | None = None) -> None:
        ttl = ttl or self._default_ttl
        self._locks[key] = time.time() + ttl


class _RedisLockManager(LockManager):
    """Redis-based distributed lock backend."""

    def __init__(self, redis_url: str) -> None:
        import redis.asyncio as aioredis
        self._r = aioredis.from_url(redis_url, decode_responses=True)

    async def acquire_lock(self, key: str, ttl: int) -> bool:
        result = await self._r.set(key, "1", nx=True, ex=ttl)
        return bool(result)

    async def release_lock(self, key: str) -> None:
        await self._r.delete(key)

    async def refresh_lock(self, key: str, ttl: int) -> None:
        await self._r.expire(key, ttl)


_settings = get_settings()
_use_redis = bool(_settings.redis_url)

_lock_manager: LockManager
if _use_redis:
    _lock_manager = _RedisLockManager(str(_settings.redis_url))
else:
    _lock_manager = _InMemoryLockManager()

_IN_MEMORY_TTL = 30


async def acquire_lock(key: str, ttl: int = _IN_MEMORY_TTL) -> bool:
    return await _lock_manager.acquire_lock(key, ttl)


async def release_lock(key: str) -> None:
    await _lock_manager.release_lock(key)


async def refresh_lock(key: str, ttl: int = _IN_MEMORY_TTL) -> None:
    await _lock_manager.refresh_lock(key, ttl)


def lock_key_workflow(workflow_id: uuid.UUID) -> str:
    return f"lock:workflow:{workflow_id}"


def lock_key_entity(entity_type: str, entity_id: str) -> str:
    return f"lock:entity:{entity_type}:{entity_id}"


@asynccontextmanager
async def workflow_lock(workflow_id: uuid.UUID) -> AsyncIterator[bool]:
    key = lock_key_workflow(workflow_id)
    acquired = await acquire_lock(key)
    try:
        yield acquired
    finally:
        if acquired:
            await release_lock(key)
