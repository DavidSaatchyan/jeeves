from __future__ import annotations

import logging
from typing import Any

import stripe as stripe_lib

from ...config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()
stripe_lib.api_key = _settings.stripe_secret_key


async def get_invoice(invoice_id: str) -> dict[str, Any] | None:
    try:
        invoice = stripe_lib.Invoice.retrieve(invoice_id)
        return _normalize_invoice(invoice)
    except stripe_lib.error.StripeError as e:
        logger.error("stripe get_invoice failed: %s", e)
        return None


async def retry_payment(invoice_id: str, idempotency_key: str) -> dict[str, Any] | None:
    try:
        invoice = stripe_lib.Invoice.pay(
            invoice_id,
            idempotency_key=idempotency_key,
        )
        return _normalize_invoice(invoice)
    except stripe_lib.error.StripeError as e:
        logger.error("stripe retry_payment failed: %s", e)
        return None


async def get_customer(customer_id: str) -> dict[str, Any] | None:
    try:
        customer = stripe_lib.Customer.retrieve(customer_id)
        return {
            "id": customer.id,
            "email": getattr(customer, "email", ""),
            "name": getattr(customer, "name", ""),
            "invoice_prefix": getattr(customer, "invoice_prefix", ""),
        }
    except stripe_lib.error.StripeError as e:
        logger.error("stripe get_customer failed: %s", e)
        return None


async def get_payment_method(customer_id: str) -> dict[str, Any] | None:
    try:
        methods = stripe_lib.PaymentMethod.list(customer=customer_id, limit=1)
        if methods and methods.data:
            pm = methods.data[0]
            return {
                "id": pm.id,
                "type": pm.type,
                "card_brand": getattr(pm, "card", {}).get("brand", "") if pm.type == "card" else "",
                "last4": getattr(pm, "card", {}).get("last4", "") if pm.type == "card" else "",
            }
        return None
    except stripe_lib.error.StripeError as e:
        logger.error("stripe get_payment_method failed: %s", e)
        return None


def _normalize_invoice(invoice: Any) -> dict[str, Any]:
    return {
        "id": invoice.id,
        "number": getattr(invoice, "number", ""),
        "status": invoice.status,
        "amount_due": invoice.amount_due / 100.0,
        "amount_paid": invoice.amount_paid / 100.0,
        "currency": invoice.currency,
        "due_date": invoice.due_date,
        "customer": getattr(invoice, "customer", ""),
        "subscription": getattr(invoice, "subscription", ""),
        "hosted_invoice_url": getattr(invoice, "hosted_invoice_url", ""),
        "invoice_pdf": getattr(invoice, "invoice_pdf", ""),
    }
