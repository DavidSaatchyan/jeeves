from __future__ import annotations

from typing import Any


def render_payment_update(context: dict[str, Any]) -> dict[str, str]:
    customer_name = context.get("customer_name", "there")
    amount = context.get("amount", "")
    plan = context.get("plan_name", "subscription")

    return {
        "subject": f"Action needed: {plan} payment update",
        "body": (
            f"Hi {customer_name},\n\n"
            f"We had trouble processing your payment of {amount} for {plan}.\n"
            f"Please update your payment method to continue your subscription.\n\n"
            f"Thank you,\nJeeves Support"
        ),
    }


def render_retry_reminder(context: dict[str, Any]) -> dict[str, str]:
    customer_name = context.get("customer_name", "there")
    amount = context.get("amount", "")
    next_attempt = context.get("next_attempt", "soon")

    return {
        "subject": "Retry reminder: we'll try again " + next_attempt,
        "body": (
            f"Hi {customer_name},\n\n"
            f"We'll retry your payment of {amount} {next_attempt}.\n"
            f"No action needed, but you can update your payment method anytime.\n\n"
            f"Thank you,\nJeeves Support"
        ),
    }


def render_auth_assistance(context: dict[str, Any]) -> dict[str, str]:
    customer_name = context.get("customer_name", "there")
    bank_name = context.get("bank_name", "your bank")

    return {
        "subject": "Authentication needed for payment",
        "body": (
            f"Hi {customer_name},\n\n"
            f"Your payment was declined due to authentication requirements from {bank_name}.\n"
            f"Please contact {bank_name} or try a different payment method.\n\n"
            f"Thank you,\nJeeves Support"
        ),
    }


def render_save_offer(context: dict[str, Any]) -> dict[str, str]:
    customer_name = context.get("customer_name", "there")
    offer_type = context.get("offer_type", "pause")

    if offer_type == "pause":
        body = f"Hi {customer_name},\n\nWe can pause your subscription instead of cancelling."
    elif offer_type == "skip":
        body = f"Hi {customer_name},\n\nWe can skip your next shipment instead of cancelling."
    elif offer_type == "delay":
        body = f"Hi {customer_name},\n\nWe can delay your renewal instead of cancelling."
    else:
        body = f"Hi {customer_name},\n\nWe have options to help before you cancel."

    return {
        "subject": "Before you go — here's an option",
        "body": body + "\n\nLet us know what works for you.\n\nThank you,\nJeeves Support",
    }
