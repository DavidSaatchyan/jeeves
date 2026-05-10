from __future__ import annotations

import logging
from typing import Any

from ...crypto import ConnectorError

logger = logging.getLogger(__name__)


def _stripe(credentials: dict):
    import stripe as stripe_lib
    stripe_lib.api_key = credentials.get("secret_key", "")
    return stripe_lib


async def get_invoice(credentials: dict, invoice_id: str) -> dict[str, Any] | None:
    try:
        invoice = _stripe(credentials).Invoice.retrieve(invoice_id)
        return {
            "id": invoice.id,
            "status": invoice.status,
            "amount_due": invoice.amount_due,
            "amount_paid": invoice.amount_paid,
            "currency": invoice.currency,
            "due_date": invoice.due_date,
            "paid_at": invoice.status_transitions.paid_at if invoice.status_transitions else None,
            "last_failure_reason": invoice.last_failure_reason or (invoice.last_payment_error.message if invoice.last_payment_error else None),
            "payment_intent": invoice.payment_intent,
        }
    except Exception as e:
        logger.error("stripe get_invoice failed: %s", e)
        return None


async def retry_payment(credentials: dict, invoice_id: str, idempotency_key: str) -> dict[str, Any] | None:
    try:
        invoice = _stripe(credentials).Invoice.pay(
            invoice_id,
            idempotency_key=idempotency_key,
        )
        return {
            "id": invoice.id,
            "status": invoice.status,
            "amount_paid": invoice.amount_paid,
            "paid_at": invoice.status_transitions.paid_at if invoice.status_transitions else None,
        }
    except Exception as e:
        logger.error("stripe retry_payment failed: %s", e)
        return None


async def get_customer(credentials: dict, customer_id: str) -> dict[str, Any] | None:
    try:
        customer = _stripe(credentials).Customer.retrieve(customer_id)
        return {
            "id": customer.id,
            "email": customer.email,
            "name": customer.name,
            "phone": customer.phone,
            "livemode": customer.livemode,
        }
    except Exception as e:
        logger.error("stripe get_customer failed: %s", e)
        return None


async def get_payment_method(credentials: dict, customer_id: str) -> dict[str, Any] | None:
    try:
        methods = _stripe(credentials).PaymentMethod.list(customer=customer_id, limit=1)
        if methods and methods.data:
            pm = methods.data[0]
            return {
                "id": pm.id,
                "type": pm.type,
                "card": pm.card if pm.type == "card" else None,
                "billing_details": pm.billing_details,
            }
        return None
    except Exception as e:
        logger.error("stripe get_payment_method failed: %s", e)
        return None
