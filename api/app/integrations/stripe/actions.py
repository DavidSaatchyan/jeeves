from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .client import retry_payment, get_invoice, get_customer, get_payment_method
from ..credentials import get_credentials
from ...shared.idempotency import idempotency_check, idempotency_set

__all__ = ["execute_retry_payment", "fetch_invoice_state", "fetch_customer_data", "fetch_payment_method_data"]


async def execute_retry_payment(tenant_id: Any, invoice_id: str, attempt: int, db: Session) -> dict | None:
    creds = get_credentials(tenant_id, "stripe", db)
    idem_key = f"payment_retry:{invoice_id}:{attempt}"
    is_dup, cached = await idempotency_check(idem_key, None)
    if is_dup:
        return cached

    result = await retry_payment(creds, invoice_id, idem_key)
    if result:
        await idempotency_set(idem_key, result)
    return result


async def fetch_invoice_state(tenant_id: Any, invoice_id: str, db: Session) -> dict | None:
    creds = get_credentials(tenant_id, "stripe", db)
    idem_key = f"invoice_state:{invoice_id}"
    is_dup, cached = await idempotency_check(idem_key, None)
    if is_dup:
        return cached

    result = await get_invoice(creds, invoice_id)
    if result:
        await idempotency_set(idem_key, result, ttl=60)
    return result


async def fetch_customer_data(tenant_id: Any, customer_id: str, db: Session) -> dict | None:
    creds = get_credentials(tenant_id, "stripe", db)
    return await get_customer(creds, customer_id)


async def fetch_payment_method_data(tenant_id: Any, customer_id: str, db: Session) -> dict | None:
    creds = get_credentials(tenant_id, "stripe", db)
    return await get_payment_method(creds, customer_id)
