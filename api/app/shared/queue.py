from __future__ import annotations

import json
import logging
from typing import Any, Callable

from ..config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()
_use_redis = bool(_settings.redis_url)

if _use_redis:
    import redis.asyncio as aioredis
    _r: aioredis.Redis | None = aioredis.from_url(_settings.redis_url, decode_responses=True)
else:
    _r = None

_QUEUE_PREFIX = "queue:"


async def enqueue(queue_name: str, payload: dict[str, Any]) -> None:
    key = f"{_QUEUE_PREFIX}{queue_name}"
    data = json.dumps(payload, default=str)
    if _use_redis and _r is not None:
        await _r.rpush(key, data)
    else:
        logger.warning("queue %s: no redis, item dropped", queue_name)


async def dequeue(queue_name: str) -> dict[str, Any] | None:
    key = f"{_QUEUE_PREFIX}{queue_name}"
    if _use_redis and _r is not None:
        raw = await _r.lpop(key)
        if raw:
            return json.loads(raw)
        return None
    logger.warning("queue %s: no redis, dequeue skipped", queue_name)
    return None


async def queue_length(queue_name: str) -> int:
    key = f"{_QUEUE_PREFIX}{queue_name}"
    if _use_redis and _r is not None:
        return await _r.llen(key)
    return 0


async def worker_loop(queue_name: str, handler: Callable[[dict[str, Any]], Any], poll_interval: int = 1) -> None:
    import asyncio

    logger.info("worker loop started for queue: %s", queue_name)
    while True:
        try:
            item = await dequeue(queue_name)
            if item:
                await handler(item)
            else:
                await asyncio.sleep(poll_interval)
        except Exception as e:
            logger.exception("worker loop error on queue %s: %s", queue_name, e)
            await asyncio.sleep(poll_interval)
