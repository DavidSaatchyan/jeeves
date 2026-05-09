from __future__ import annotations

from typing import Any

from ...core.events.schemas import CanonicalEvent

EVENT_TYPE_MAP = {
    "subscription_created": "subscription_created",
    "subscription_updated": "subscription_updated",
    "subscription_cancelled": "subscription_cancel_requested",
    "subscription_paused": "subscription_paused",
    "subscription_skipped": "subscription_skipped",
    "subscription_delayed": "subscription_delayed",
    "charge_failed": "rebill_failed",
    "charge_success": "payment_recovered",
}

SOURCE = "recharge"


def normalize_webhook(payload: dict[str, Any], tenant_id: str) -> CanonicalEvent | None:
    raw_type = payload.get("event", {}).get("type", "")
    event_type = EVENT_TYPE_MAP.get(raw_type)
    if not event_type:
        return None

    data = payload.get("event", {}).get("data", {}).get("object", payload)
    entity_id = data.get("id", "") or data.get("subscription_id", "")

    return CanonicalEvent(
        tenant_id=tenant_id,
        event_type=event_type,
        event_source=SOURCE,
        entity_type="subscription",
        entity_id=str(entity_id),
        payload={
            "customer_id": str(data.get("customer_id", "")),
            "subscription_id": str(data.get("subscription_id", "") or data.get("id", "")),
            "status": data.get("status", ""),
            "raw_type": raw_type,
        },
    )
