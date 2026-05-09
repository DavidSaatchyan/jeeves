from __future__ import annotations

from .client import get_customer, get_order, get_fulfillment, get_orders_by_customer
from ...shared.idempotency import idempotency_check, idempotency_set

__all__ = [
    "fetch_customer",
    "fetch_order",
    "fetch_fulfillments",
    "fetch_customer_orders",
]


async def fetch_customer(customer_id: str) -> dict | None:
    return await get_customer(customer_id)


async def fetch_order(order_id: str) -> dict | None:
    idem_key = f"shopify_order:{order_id}"
    is_dup, cached = await idempotency_check(idem_key, None)
    if is_dup:
        return cached
    result = await get_order(order_id)
    if result:
        await idempotency_set(idem_key, result, ttl=60)
    return result


async def fetch_fulfillments(order_id: str) -> list[dict]:
    return await get_fulfillment(order_id)


async def fetch_customer_orders(customer_id: str, limit: int = 10) -> list[dict]:
    return await get_orders_by_customer(customer_id, limit)
