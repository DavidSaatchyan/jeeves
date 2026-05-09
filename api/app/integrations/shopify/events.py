from __future__ import annotations

from typing import Any

from ...core.events.schemas import CanonicalEvent

EVENT_TYPE_MAP = {
    "orders/create": "order_created",
    "orders/updated": "order_updated",
    "orders/fulfilled": "order_fulfilled",
    "orders/cancelled": "order_cancelled",
    "customers/create": "customer_created",
    "customers/update": "customer_updated",
    "fulfillments/create": "fulfillment_created",
    "fulfillments/update": "tracking_updated",
}

SOURCE = "shopify"


def normalize_webhook(payload: dict[str, Any], tenant_id: str) -> CanonicalEvent | None:
    raw_type = payload.get("topic", "")
    event_type = EVENT_TYPE_MAP.get(raw_type)
    if not event_type:
        return None

    data = payload.get("data", payload)
    entity_id = str(data.get("id", ""))

    if raw_type.startswith("orders/"):
        entity_type = "order"
    elif raw_type.startswith("customers/"):
        entity_type = "customer"
    elif raw_type.startswith("fulfillments/"):
        entity_type = "fulfillment"
    else:
        entity_type = "unknown"

    return CanonicalEvent(
        tenant_id=tenant_id,
        event_type=event_type,
        event_source=SOURCE,
        entity_type=entity_type,
        entity_id=entity_id,
        payload={
            "customer_id": str(data.get("customer", {}).get("id", "")),
            "order_id": entity_id,
            "status": data.get("financial_status", "") or data.get("status", ""),
            "raw_topic": raw_type,
        },
    )
