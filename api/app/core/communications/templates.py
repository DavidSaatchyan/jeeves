from __future__ import annotations

from typing import Any


def render_tracking_update(context: dict[str, Any]) -> dict[str, str]:
    return {
        "subject": f"Your Order {context.get('order_name', '')} — On Track",
        "body": (
            f"Hi {context.get('customer_name', 'there')},\n\n"
            f"Good news! Your order {context.get('order_name', '')} is on track for delivery."
            + (f"\nEstimated delivery: {context['estimated_delivery']}." if context.get("estimated_delivery") else "")
            + "\n\nWe'll notify you when it's delivered.\n\n- Your Support Team"
        ),
    }


def render_delay_notification(context: dict[str, Any]) -> dict[str, str]:
    reason = context.get("reason", "")
    est = context.get("estimated_delivery", "")
    body = (
        f"Hi {context.get('customer_name', 'there')},\n\n"
        f"We wanted to let you know that your order {context.get('order_name', '')} is experiencing a delay."
    )
    if reason:
        body += f"\n\nReason: {reason}"
    if est:
        body += f"\n\nYour new estimated delivery date is {est}."
    body += "\n\nWe apologize for the inconvenience.\n\n- Your Support Team"
    return {
        "subject": f"Update on Your Order {context.get('order_name', '')} — Delayed",
        "body": body,
    }


def render_delivery_confirmation(context: dict[str, Any]) -> dict[str, str]:
    return {
        "subject": f"Your Order {context.get('order_name', '')} — Delivered!",
        "body": (
            f"Hi {context.get('customer_name', 'there')},\n\n"
            f"Your order {context.get('order_name', '')} has been delivered! We hope you love it."
            "\n\nThanks for shopping with us.\n\n- Your Support Team"
        ),
    }


def render_lost_package(context: dict[str, Any]) -> dict[str, str]:
    return {
        "subject": f"Urgent: Order {context.get('order_name', '')} — Lost in Transit",
        "body": (
            f"Hi {context.get('customer_name', 'there')},\n\n"
            f"We're very sorry — it appears your order {context.get('order_name', '')} has been lost in transit.\n"
            "We've notified our support team, and they will reach out to you within 24 hours "
            "with a resolution (replacement or refund).\n\n"
            "We sincerely apologize for this experience.\n\n- Your Support Team"
        ),
    }
