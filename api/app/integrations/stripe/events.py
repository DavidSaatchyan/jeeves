from __future__ import annotations

from typing import Any

from ...core.events.schemas import CanonicalEvent

EVENT_TYPE_MAP = {
    "invoice.payment_failed": "payment_failed",
    "invoice.payment_succeeded": "payment_recovered",
    "customer.subscription.updated": "subscription_updated",
    "customer.subscription.deleted": "subscription_cancel_requested",
}

SOURCE = "stripe"


def normalize_webhook(payload: dict[str, Any], tenant_id: str) -> CanonicalEvent | None:
    event_type_raw = payload.get("type", "")
    event_type = EVENT_TYPE_MAP.get(event_type_raw)
    if not event_type:
        return None

    data = payload.get("data", {}).get("object", {})
    entity_type = _detect_entity_type(event_type_raw)
    entity_id = data.get("id", "")

    return CanonicalEvent(
        tenant_id=tenant_id,
        event_type=event_type,
        event_source=SOURCE,
        entity_type=entity_type,
        entity_id=entity_id,
        payload={
            "customer_id": data.get("customer", ""),
            "subscription_id": data.get("subscription", ""),
            "amount_due": data.get("amount_due"),
            "currency": data.get("currency"),
            "status": data.get("status"),
            "raw_type": event_type_raw,
        },
    )


def _detect_entity_type(event_type_raw: str) -> str:
    if event_type_raw.startswith("invoice."):
        return "invoice"
    if event_type_raw.startswith("customer.subscription"):
        return "subscription"
    if event_type_raw.startswith("payment_method"):
        return "payment_method"
    return "unknown"
