from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from ...shared.idempotency import idempotency_get, idempotency_set

logger = logging.getLogger(__name__)


@asynccontextmanager
async def execution_idempotent(key: str, ttl: int = 86400) -> AsyncIterator[bool]:
    existing = await idempotency_get(key)
    if existing is not None:
        logger.info("idempotent execution skipped: %s", key)
        yield False
    else:
        await idempotency_set(key, "executing", ttl=ttl)
        try:
            yield True
        except Exception:
            await idempotency_set(key, "failed", ttl=ttl)
            raise
        else:
            await idempotency_set(key, "completed", ttl=ttl)
