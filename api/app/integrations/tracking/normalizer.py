from __future__ import annotations

from typing import Any

CARRIER_STATE_MAP: dict[str, dict[str, str]] = {
    "shopify": {
        "fulfilled": "in_transit",
        "in_transit": "in_transit",
        "out_for_delivery": "in_transit",
        "delivered": "delivered",
        "attempted_delivery": "exception",
        "ready_for_pickup": "in_transit",
        "picked_up": "delivered",
        "label_printed": "processing",
        "label_purchased": "processing",
        "cancelled": "exception",
        "error": "exception",
    },
}

CANONICAL_STATES = ["processing", "fulfilled", "in_transit", "delayed", "exception", "delivered", "unknown"]


def normalize_carrier_state(carrier: str, carrier_state: str) -> str:
    mapping = CARRIER_STATE_MAP.get(carrier, {})
    canonical = mapping.get(carrier_state, "unknown")
    if canonical not in CANONICAL_STATES:
        return "unknown"
    return canonical


def normalize_tracking_event(payload: dict[str, Any]) -> dict[str, Any]:
    carrier = payload.get("carrier", "unknown")
    raw_state = payload.get("status", payload.get("event", ""))
    canonical_state = normalize_carrier_state(carrier, raw_state)

    return {
        "tracking_number": payload.get("tracking_number", ""),
        "carrier": carrier,
        "raw_state": raw_state,
        "canonical_state": canonical_state,
        "estimated_delivery": payload.get("estimated_delivery", payload.get("eta", "")),
        "location": payload.get("location", {}),
        "timestamp": payload.get("timestamp", payload.get("occurred_at", "")),
    }
