"""Rate limiting middleware for sensitive endpoints.

Uses Redis if available, falls back to in-memory dict for dev.
Limits:
  - login: 5 attempts per minute per IP
  - register: 3 per hour per IP
  - chat/widget: 20 per minute per IP
"""
from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any

logger = logging.getLogger("jeeves.shared.rate_limit")


class RateLimiter(ABC):
    """Abstract interface for rate-limiting backends."""

    @abstractmethod
    async def is_allowed(self, key: str, max_count: int, window: int) -> bool:
        ...


class _InMemoryLimiter(RateLimiter):
    """Thread-safe in-memory sliding window rate limiter for dev/single-process."""

    def __init__(self) -> None:
        self._buckets: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    async def is_allowed(self, key: str, max_count: int, window: int) -> bool:
        now = time.time()
        cutoff = now - window
        with self._lock:
            bucket = self._buckets[key]
            self._buckets[key] = [t for t in bucket if t > cutoff]
            if len(self._buckets[key]) >= max_count:
                return False
            self._buckets[key].append(now)
            return True


_limiter: RateLimiter | None = None

def _get_limiter():
    global _limiter
    if _limiter is not None:
        return _limiter
    try:
        from ..config import get_settings
        settings = get_settings()
        if settings.redis_url:
            import redis
            r = redis.from_url(settings.redis_url, decode_responses=True)
            r.ping()
            _limiter = _RedisLimiter(r)
            return _limiter
    except Exception:
        pass
    logger.info("Redis unavailable — falling back to in-memory rate limiter")
    _limiter = _InMemoryLimiter()
    return _limiter


class _RedisLimiter(RateLimiter):
    """Redis-based sliding window rate limiter."""

    def __init__(self, client: Any) -> None:
        self._r = client

    async def is_allowed(self, key: str, max_count: int, window: int) -> bool:
        now = time.time()
        cutoff = now - window
        pipe = self._r.pipeline()
        pipe.zremrangebyscore(key, 0, cutoff)
        pipe.zcard(key)
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, window + 10)
        results = pipe.execute()
        count = results[1]
        return count < max_count


# Endpoint-specific limits
_LIMITS = {
    "login": (5, 60),        # 5 per minute
    "register": (3, 3600),   # 3 per hour
    "chat": (20, 60),        # 20 per minute
    "widget": (20, 60),      # 20 per minute
    "whatsapp": (30, 60),    # 30 per minute per WA ID
}


async def check_rate_limit(endpoint: str, ip: str) -> bool:
    """Return True if request is allowed, False if rate limited."""
    if endpoint not in _LIMITS:
        return True
    max_req, window = _LIMITS[endpoint]
    key = f"ratelimit:{endpoint}:{ip}"
    return await _get_limiter().is_allowed(key, max_req, window)
