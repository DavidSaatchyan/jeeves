from __future__ import annotations

from .client import (
    pause_subscription,
    skip_next_shipment,
    delay_renewal,
    cancel_subscription,
    get_subscription,
)
from ...shared.idempotency import idempotency_check, idempotency_set

__all__ = [
    "execute_pause_subscription",
    "execute_skip_shipment",
    "execute_delay_renewal",
    "execute_cancel_subscription",
    "fetch_subscription_state",
]


async def execute_pause_subscription(subscription_id: str, pause_note: str = "") -> dict | None:
    idem_key = f"subscription_mutation:{subscription_id}:pause"
    is_dup, cached = await idempotency_check(idem_key, None)
    if is_dup:
        return cached
    result = await pause_subscription(subscription_id, pause_note)
    if result:
        await idempotency_set(idem_key, result)
    return result


async def execute_skip_shipment(subscription_id: str) -> dict | None:
    idem_key = f"subscription_mutation:{subscription_id}:skip"
    is_dup, cached = await idempotency_check(idem_key, None)
    if is_dup:
        return cached
    result = await skip_next_shipment(subscription_id)
    if result:
        await idempotency_set(idem_key, result)
    return result


async def execute_delay_renewal(subscription_id: str, delay_days: int = 7) -> dict | None:
    idem_key = f"subscription_mutation:{subscription_id}:delay_{delay_days}"
    is_dup, cached = await idempotency_check(idem_key, None)
    if is_dup:
        return cached
    result = await delay_renewal(subscription_id, delay_days)
    if result:
        await idempotency_set(idem_key, result)
    return result


async def execute_cancel_subscription(subscription_id: str, reason: str = "") -> dict | None:
    return await cancel_subscription(subscription_id, reason)


async def fetch_subscription_state(subscription_id: str) -> dict | None:
    return await get_subscription(subscription_id)
