from __future__ import annotations

import asyncio
import logging
import time
from functools import wraps
from typing import Any, Callable

logger = logging.getLogger("jeeves.timer")


def timed(stage: str) -> Callable:
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                return await fn(*args, **kwargs)
            finally:
                elapsed = (time.perf_counter() - start) * 1000
                logger.info("timed:stage=%s latency_ms=%.1f", stage, elapsed)

        @wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                elapsed = (time.perf_counter() - start) * 1000
                logger.info("timed:stage=%s latency_ms=%.1f", stage, elapsed)

        if asyncio.iscoroutinefunction(fn):
            return async_wrapper
        return sync_wrapper
    return decorator
