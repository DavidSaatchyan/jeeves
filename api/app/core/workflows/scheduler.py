from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from ...config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()
_use_redis = bool(_settings.redis_url)

if _use_redis:
    import redis.asyncio as aioredis
    _r: aioredis.Redis | None = aioredis.from_url(_settings.redis_url, decode_responses=True)
else:
    _r = None

_SCHEDULE_PREFIX = "schedule:"


async def schedule_job(job_type: str, execute_at: datetime, payload: dict[str, Any]) -> str:
    import uuid
    job_id = uuid.uuid4().hex
    key = f"{_SCHEDULE_PREFIX}{job_type}:{job_id}"

    job_data = {
        "job_id": job_id,
        "job_type": job_type,
        "execute_at": execute_at.isoformat(),
        "payload": payload,
    }

    if _use_redis and _r is not None:
        ttl = max(int((execute_at - datetime.utcnow()).total_seconds()), 60)
        await _r.setex(key, ttl, json.dumps(job_data, default=str))
        await _r.zadd(f"{_SCHEDULE_PREFIX}index", {key: execute_at.timestamp()})
    else:
        pass

    return job_id


async def cancel_job(job_type: str, job_id: str) -> None:
    key = f"{_SCHEDULE_PREFIX}{job_type}:{job_id}"
    if _use_redis and _r is not None:
        await _r.delete(key)
        await _r.zrem(f"{_SCHEDULE_PREFIX}index", key)


async def get_due_jobs() -> list[dict[str, Any]]:
    if _use_redis and _r is not None:
        now = datetime.utcnow().timestamp()
        due = await _r.zrangebyscore(f"{_SCHEDULE_PREFIX}index", 0, now)
        jobs = []
        for key in due:
            raw = await _r.get(key)
            if raw:
                jobs.append(json.loads(raw))
                await _r.delete(key)
            await _r.zrem(f"{_SCHEDULE_PREFIX}index", key)
        return jobs
    return []
