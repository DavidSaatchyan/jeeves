from __future__ import annotations

import logging
from typing import Any, Callable

from ...shared.idempotency import idempotency_check, idempotency_set

logger = logging.getLogger(__name__)


async def execute_action(action_fn: Callable, action_name: str, idempotency_key: str, *args, **kwargs) -> dict[str, Any] | None:
    is_dup, cached = await idempotency_check(idempotency_key, None)
    if is_dup:
        logger.info("duplicate action skipped: %s (%s)", action_name, idempotency_key)
        return cached

    try:
        result = await action_fn(*args, **kwargs)
        if result:
            await idempotency_set(idempotency_key, result)
        return result
    except Exception as e:
        logger.error("action %s failed: %s", action_name, e)
        raise
