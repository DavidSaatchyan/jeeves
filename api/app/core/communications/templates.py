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


def render_campaign_first_contact(context: dict[str, Any]) -> dict[str, str]:
    name = context.get("patient_name", "there")
    clinic = context.get("clinic_name", "our clinic")
    service = context.get("service", "health services")
    return {
        "subject": f"Special offer from {clinic}",
        "body": (
            f"Hi {name}! This is {clinic}. We have some great news about our {service}. "
            f"Would you like to learn more? Reply STOP to opt out."
        ),
    }


def render_campaign_nurture(context: dict[str, Any]) -> dict[str, str]:
    name = context.get("patient_name", "there")
    clinic = context.get("clinic_name", "our clinic")
    return {
        "subject": f"Follow-up from {clinic}",
        "body": (
            f"Hi {name}! Just following up on our previous message. "
            f"At {clinic}, we care about your health. "
            f"Would you like to schedule a visit? Reply STOP to opt out."
        ),
    }


def render_followup_day1(context: dict[str, Any]) -> dict[str, str]:
    name = context.get("patient_name", "there")
    clinic = context.get("clinic_name", "your clinic")
    return {
        "subject": f"How are you feeling? — {clinic}",
        "body": (
            f"Hi {name}! Just checking in after your recent visit to {clinic}. "
            f"How are you feeling today? Reply STOP to opt out."
        ),
    }


def render_followup_day7(context: dict[str, Any]) -> dict[str, str]:
    name = context.get("patient_name", "there")
    return {
        "subject": "One week check-in",
        "body": (
            f"Hi {name}! It's been a week since your visit. "
            f"We hope you're doing well. Any concerns or questions? Reply STOP to opt out."
        ),
    }


def render_followup_day30(context: dict[str, Any]) -> dict[str, str]:
    name = context.get("patient_name", "there")
    clinic = context.get("clinic_name", "your clinic")
    return {
        "subject": "One month check-in",
        "body": (
            f"Hi {name}! It's been a month since your visit to {clinic}. "
            f"How are you feeling? Are you satisfied with your progress? Reply STOP to opt out."
        ),
    }


def render_medication_adherence(context: dict[str, Any]) -> dict[str, str]:
    name = context.get("patient_name", "there")
    return {
        "subject": "Medication reminder",
        "body": (
            f"Hi {name}! Just a friendly reminder to take your medications as prescribed. "
            f"Are you having any trouble with your treatment plan? Reply STOP to opt out."
        ),
    }


def render_satisfaction_survey(context: dict[str, Any]) -> dict[str, str]:
    name = context.get("patient_name", "there")
    clinic = context.get("clinic_name", "your clinic")
    return {
        "subject": f"We value your feedback — {clinic}",
        "body": (
            f"Hi {name}! We'd love your feedback about your experience at {clinic}. "
            f"On a scale of 1-10, how likely are you to recommend us? "
            f"Reply STOP to opt out."
        ),
    }
