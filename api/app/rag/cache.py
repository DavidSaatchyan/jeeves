"""Semantic cache — Redis + in-memory LRU fallback."""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from typing import Any

from ..config import get_settings
from .client import embed_batch
from .config import SEMANTIC_CACHE

logger = logging.getLogger(__name__)

_COSINE_THRESHOLD = 0.95
_CACHE_TTL_SECONDS = 86400  # 24h
_IN_MEMORY_MAX = 1000


class _InMemoryCache:
    def __init__(self, maxsize: int = _IN_MEMORY_MAX):
        self._store: OrderedDict[str, tuple[float, list[dict[str, Any]]]] = OrderedDict()
        self._maxsize = maxsize
        self._lock = threading.Lock()

    def get(self, key: str) -> list[dict[str, Any]] | None:
        with self._lock:
            if key not in self._store:
                return None
            expires, value = self._store[key]
            if time.time() > expires:
                del self._store[key]
                return None
            self._store.move_to_end(key)
            return value

    def set(self, key: str, value: list[dict[str, Any]], ttl: int = _CACHE_TTL_SECONDS) -> None:
        with self._lock:
            self._store[key] = (time.time() + ttl, value)
            self._store.move_to_end(key)
            while len(self._store) > self._maxsize:
                self._store.popitem(last=False)


_in_memory: _InMemoryCache = _InMemoryCache()
_redis = None
_redis_lock = threading.Lock()


def _get_redis():
    global _redis
    if _redis is not None:
        return _redis
    settings = get_settings()
    if not settings.redis_url:
        return None
    with _redis_lock:
        if _redis is not None:
            return _redis
        try:
            import redis as redis_mod
            _redis = redis_mod.from_url(settings.redis_url, decode_responses=True)
            _redis.ping()
            logger.info("Semantic cache connected to Redis")
        except Exception as e:
            logger.warning("Redis unavailable for semantic cache: %s", e)
            _redis = None
        return _redis


def _make_cache_key(query: str) -> str:
    return f"rag_cache:{hashlib.md5(query.encode()).hexdigest()}"


def _cosine_sim(a: list[float], b: list[float]) -> float:
    import math
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def cache_lookup(query: str) -> list[dict[str, Any]] | None:
    if not SEMANTIC_CACHE:
        return None
    try:
        q_emb = embed_batch([query])[0]
    except Exception as e:
        logger.error("Cache lookup embedding failed: %s", e)
        return None

    cache_key = _make_cache_key(query)

    r = _get_redis()
    if r is not None:
        try:
            stored = r.get(cache_key)
            if stored:
                data: dict = json.loads(stored)
                cached_emb = data.get("embedding", [])
                if cached_emb and _cosine_sim(q_emb, cached_emb) >= _COSINE_THRESHOLD:
                    logger.info("Semantic cache HIT for query=%s", query[:60])
                    return data.get("results", [])
        except Exception as e:
            logger.warning("Redis cache lookup failed: %s", e)

    cached = _in_memory.get(cache_key)
    if cached is not None:
        logger.info("In-memory cache HIT for query=%s", query[:60])
        return cached
    return None


def cache_store(query: str, results: list[dict[str, Any]]) -> None:
    if not SEMANTIC_CACHE:
        return
    try:
        q_emb = embed_batch([query])[0]
    except Exception as e:
        logger.error("Cache store embedding failed: %s", e)
        return

    cache_key = _make_cache_key(query)

    r = _get_redis()
    if r is not None:
        try:
            payload = json.dumps({"embedding": q_emb, "results": results}, default=str)
            r.setex(cache_key, _CACHE_TTL_SECONDS, payload)
        except Exception as e:
            logger.warning("Redis cache store failed: %s", e)

    _in_memory.set(cache_key, results)


def invalidate_cache() -> None:
    logger.info("Semantic cache invalidated")
    r = _get_redis()
    if r is not None:
        try:
            for key in r.scan_iter("rag_cache:*"):
                r.delete(key)
        except Exception as e:
            logger.warning("Redis cache invalidation failed: %s", e)
