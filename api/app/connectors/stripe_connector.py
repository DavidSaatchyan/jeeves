"""Stripe connector.

Credentials dict: {"secret_key": "sk_..."}
Uses the stripe Python SDK. api_key is set per-call, never globally.
Sync SDK calls are wrapped with asyncio.to_thread.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import stripe as stripe_lib

from ..crypto import ConnectorError


def _set_key(credentials: dict) -> None:
    """Set stripe.api_key from credentials for the current call."""
    stripe_lib.api_key = credentials["secret_key"]


async def get_subscription(credentials: dict, customer_email: str) -> dict:
    """Find customer by email, return active subscription details.

    Returns: {subscription_id, plan_name, status, current_period_end}
    """
    _set_key(credentials)

    try:
        # Find customer by email
        customers = await asyncio.to_thread(
            stripe_lib.Customer.list, email=customer_email, limit=1
        )
        if not customers.data:
            return {}

        customer = customers.data[0]

        # Get active subscriptions for the customer
        subscriptions = await asyncio.to_thread(
            stripe_lib.Subscription.list,
            customer=customer.id,
            status="active",
            limit=1,
        )
        if not subscriptions.data:
            return {}

        sub = subscriptions.data[0]
        plan_name = ""
        if sub.items and sub.items.data:
            price = sub.items.data[0].price
            plan_name = price.nickname or price.id or ""

        return {
            "subscription_id": sub.id,
            "plan_name": plan_name,
            "status": sub.status,
            "current_period_end": datetime.fromtimestamp(
                sub.current_period_end, tz=timezone.utc
            ).isoformat(),
        }
    except stripe_lib.error.StripeError as e:
        raise ConnectorError(provider="stripe", operation="get_subscription", message=str(e))


async def get_next_invoice(credentials: dict, customer_email: str) -> dict:
    """Get upcoming invoice for customer.

    Returns: {amount_due, currency, next_payment_date}
    """
    _set_key(credentials)

    try:
        # Find customer by email
        customers = await asyncio.to_thread(
            stripe_lib.Customer.list, email=customer_email, limit=1
        )
        if not customers.data:
            return {}

        customer = customers.data[0]

        invoice = await asyncio.to_thread(
            stripe_lib.Invoice.upcoming, customer=customer.id
        )

        return {
            "amount_due": invoice.amount_due,
            "currency": invoice.currency,
            "next_payment_date": datetime.fromtimestamp(
                invoice.next_payment_attempt, tz=timezone.utc
            ).isoformat()
            if invoice.next_payment_attempt
            else None,
        }
    except stripe_lib.error.StripeError as e:
        raise ConnectorError(provider="stripe", operation="get_next_invoice", message=str(e))


async def cancel_at_period_end(
    credentials: dict,
    subscription_id: str,
    idempotency_key: str,
) -> dict:
    """Modify subscription to cancel at period end.

    Passes idempotency_key to stripe.Subscription.modify.
    """
    _set_key(credentials)

    try:
        result = await asyncio.to_thread(
            stripe_lib.Subscription.modify,
            subscription_id,
            cancel_at_period_end=True,
            idempotency_key=idempotency_key,
        )
        return dict(result)
    except stripe_lib.error.StripeError as e:
        raise ConnectorError(provider="stripe", operation="cancel_at_period_end", message=str(e))
