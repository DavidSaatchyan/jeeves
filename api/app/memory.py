"""Redis-backed short-term conversation memory (FR-4.1).

Falls back to in-memory dict when no Redis URL is configured.
"""
from __future__ import annotations

import json
from collections import defaultdict, deque
from typing import List

from .config import get_settings, get_yaml_config

_settings = get_settings()
_cfg = get_yaml_config().get("memory", {})
_MAX = int(_cfg.get("max_messages", 20))
_TTL = int(_cfg.get("ttl_days", 7)) * 86400

_use_redis = bool(_settings.redis_url)
if _use_redis:
    import redis
    _r = redis.Redis.from_url(_settings.redis_url, decode_responses=True)
else:
    _mem: dict[str, deque] = defaultdict(lambda: deque(maxlen=_MAX))


def _key(tenant_id: str, user_id: str) -> str:
    return f"memory:{tenant_id}:{user_id}"


def _fallback_key(tenant_id: str, user_id: str) -> str:
    return f"{tenant_id}:{user_id}"


def append(tenant_id: str, user_id: str, role: str, content: str) -> None:
    if _use_redis:
        k = _key(tenant_id, user_id)
        _r.rpush(k, json.dumps({"role": role, "content": content}))
        _r.ltrim(k, -_MAX, -1)
        _r.expire(k, _TTL)
    else:
        k = _fallback_key(tenant_id, user_id)
        _mem[k].append({"role": role, "content": content})


def history(tenant_id: str, user_id: str) -> List[dict]:
    if _use_redis:
        k = _key(tenant_id, user_id)
        raw = _r.lrange(k, 0, -1)
        return [json.loads(x) for x in raw]
    else:
        k = _fallback_key(tenant_id, user_id)
        return list(_mem[k])
