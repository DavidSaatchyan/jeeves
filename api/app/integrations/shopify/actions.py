from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .client import get_customer, get_order, get_fulfillment, get_orders_by_customer
from ..credentials import get_credentials
from ...shared.idempotency import idempotency_check, idempotency_set

__all__ = [
    "fetch_customer",
    "fetch_order",
    "fetch_fulfillments",
    "fetch_customer_orders",
]


async def fetch_customer(tenant_id: Any, customer_id: str, db: Session) -> dict | None:
    creds = get_credentials(tenant_id, "shopify", db)
    return await get_customer(creds, customer_id)


async def fetch_order(tenant_id: Any, order_id: str, db: Session) -> dict | None:
    creds = get_credentials(tenant_id, "shopify", db)
    idem_key = f"shopify_order:{order_id}"
    is_dup, cached = await idempotency_check(idem_key, None)
    if is_dup:
        return cached
    result = await get_order(creds, order_id)
    if result:
        await idempotency_set(idem_key, result, ttl=60)
    return result


async def fetch_fulfillments(tenant_id: Any, order_id: str, db: Session) -> list[dict]:
    creds = get_credentials(tenant_id, "shopify", db)
    return await get_fulfillment(creds, order_id)


async def fetch_customer_orders(tenant_id: Any, customer_id: str, db: Session, limit: int = 10) -> list[dict]:
    creds = get_credentials(tenant_id, "shopify", db)
    return await get_orders_by_customer(creds, customer_id, limit)
