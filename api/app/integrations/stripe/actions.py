from __future__ import annotations

from .client import retry_payment, get_invoice, get_customer, get_payment_method
from ...shared.idempotency import idempotency_check, idempotency_set

__all__ = ["execute_retry_payment", "fetch_invoice_state", "fetch_customer_data", "fetch_payment_method_data"]


async def execute_retry_payment(invoice_id: str, attempt: int) -> dict | None:
    idem_key = f"payment_retry:{invoice_id}:{attempt}"
    is_dup, cached = await idempotency_check(idem_key, None)
    if is_dup:
        return cached

    result = await retry_payment(invoice_id, idem_key)
    if result:
        await idempotency_set(idem_key, result)
    return result


async def fetch_invoice_state(invoice_id: str) -> dict | None:
    idem_key = f"invoice_state:{invoice_id}"
    is_dup, cached = await idempotency_check(idem_key, None)
    if is_dup:
        return cached

    result = await get_invoice(invoice_id)
    if result:
        await idempotency_set(idem_key, result, ttl=60)
    return result


async def fetch_customer_data(customer_id: str) -> dict | None:
    return await get_customer(customer_id)


async def fetch_payment_method_data(customer_id: str) -> dict | None:
    return await get_payment_method(customer_id)
