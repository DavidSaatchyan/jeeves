from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .client import (
    pause_subscription,
    skip_next_shipment,
    delay_renewal,
    cancel_subscription,
    get_subscription,
)
from ..credentials import get_credentials
from ...shared.idempotency import idempotency_check, idempotency_set

__all__ = [
    "execute_pause_subscription",
    "execute_skip_shipment",
    "execute_delay_renewal",
    "execute_cancel_subscription",
    "fetch_subscription_state",
]


async def execute_pause_subscription(tenant_id: Any, subscription_id: str, db: Session, pause_note: str = "") -> dict | None:
    creds = get_credentials(tenant_id, "recharge", db)
    idem_key = f"subscription_mutation:{subscription_id}:pause"
    is_dup, cached = await idempotency_check(idem_key, None)
    if is_dup:
        return cached
    result = await pause_subscription(creds, subscription_id, pause_note)
    if result:
        await idempotency_set(idem_key, result)
    return result


async def execute_skip_shipment(tenant_id: Any, subscription_id: str, db: Session) -> dict | None:
    creds = get_credentials(tenant_id, "recharge", db)
    idem_key = f"subscription_mutation:{subscription_id}:skip"
    is_dup, cached = await idempotency_check(idem_key, None)
    if is_dup:
        return cached
    result = await skip_next_shipment(creds, subscription_id)
    if result:
        await idempotency_set(idem_key, result)
    return result


async def execute_delay_renewal(tenant_id: Any, subscription_id: str, db: Session, delay_days: int = 7) -> dict | None:
    creds = get_credentials(tenant_id, "recharge", db)
    idem_key = f"subscription_mutation:{subscription_id}:delay_{delay_days}"
    is_dup, cached = await idempotency_check(idem_key, None)
    if is_dup:
        return cached
    result = await delay_renewal(creds, subscription_id, delay_days)
    if result:
        await idempotency_set(idem_key, result)
    return result


async def execute_cancel_subscription(tenant_id: Any, subscription_id: str, db: Session, reason: str = "") -> dict | None:
    creds = get_credentials(tenant_id, "recharge", db)
    return await cancel_subscription(creds, subscription_id, reason)


async def fetch_subscription_state(tenant_id: Any, subscription_id: str, db: Session) -> dict | None:
    creds = get_credentials(tenant_id, "recharge", db)
    return await get_subscription(creds, subscription_id)
