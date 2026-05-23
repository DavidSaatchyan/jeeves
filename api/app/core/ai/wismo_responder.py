from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


async def generate_wismo_widget_response(classification: dict, order: dict | None = None) -> str:
    status = classification.get("status", "on_track")
    estimated = classification.get("estimated_delivery", "")
    order_name = (order or {}).get("name", "")

    if status == "delayed":
        if estimated:
            msg = f"Your order {order_name} is delayed. The new estimated delivery is {estimated}. We're sorry for the inconvenience!"
        else:
            msg = f"Your order {order_name} is delayed. We're working on it and will notify you when there's an update."
    elif status == "lost":
        msg = (f"We're sorry — your order {order_name} appears to be lost. "
               "A support specialist has been notified and will contact you shortly.")
    else:
        if estimated:
            msg = f"Good news! Your order {order_name} is on track and expected by {estimated}."
        else:
            msg = f"Your order {order_name} is on its way! We'll notify you when it's delivered."

    prompt = (
        "Rewrite this as a short, conversational widget message (1-2 sentences, max 150 chars):\n\n"
        f"{msg}\n\n"
        "Respond with JSON: {\"message\": \"...\"}"
    )

    try:
        from openai import AsyncOpenAI

        from ...config import get_settings

        client = AsyncOpenAI(api_key=get_settings().openai_api_key)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=100,
        )
        raw = response.choices[0].message.content or ""
        parsed = json.loads(raw)
        return parsed.get("message", msg)
    except Exception:
        return msg


async def generate_wismo_email(classification: dict, order: dict | None = None, customer: dict | None = None) -> dict:
    status = classification.get("status", "on_track")
    estimated = classification.get("estimated_delivery", "")
    reason = classification.get("reason", "")
    order_name = (order or {}).get("name", "")
    customer_name = (customer or {}).get("first_name", "there")

    if status == "delayed":
        lines = [
            f"Hi {customer_name},",
            "",
            f"We wanted to let you know that your order {order_name} is experiencing a delay.",
        ]
        if reason:
            lines.append(f"Reason: {reason}")
        if estimated:
            lines.append(f"Your new estimated delivery date is {estimated}.")
        lines.append("")
        lines.append("We apologize for the inconvenience and appreciate your patience.")
        lines.append("")
        lines.append("- Your Support Team")
        subject = f"Update on Your Order {order_name} — Delayed"

    elif status == "lost":
        lines = [
            f"Hi {customer_name},",
            "",
            f"We're very sorry — it appears your order {order_name} has been lost in transit.",
            "We've notified our support team, and they will reach out to you within 24 hours",
            "with a resolution (replacement or refund).",
            "",
            "We sincerely apologize for this experience.",
            "",
            "- Your Support Team",
        ]
        subject = f"Urgent: Order {order_name} — Lost in Transit"
    else:
        lines = [
            f"Hi {customer_name},",
            "",
            f"Good news! Your order {order_name} is on track for delivery.",
        ]
        if estimated:
            lines.append(f"Estimated delivery: {estimated}.")
        lines.append("")
        lines.append("We'll notify you when it's delivered.")
        lines.append("")
        lines.append("- Your Support Team")
        subject = f"Your Order {order_name} — On Track"

    body = "\n".join(lines)

    prompt = (
        "Polish this email to be warm and professional (keep the same structure):\n\n"
        f"Subject: {subject}\n\n{body}\n\n"
        "Respond with JSON: {\"subject\": \"...\", \"body\": \"...\"}"
    )

    try:
        from openai import AsyncOpenAI

        from ...config import get_settings

        client = AsyncOpenAI(api_key=get_settings().openai_api_key)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=400,
        )
        raw = response.choices[0].message.content or ""
        parsed = json.loads(raw)
        return {"subject": parsed.get("subject", subject), "body": parsed.get("body", body)}
    except Exception:
        return {"subject": subject, "body": body}
