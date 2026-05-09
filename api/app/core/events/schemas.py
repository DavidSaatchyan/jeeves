from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


EVENT_TYPES = {
    "payment_failed",
    "payment_recovered",
    "invoice_payment_failed",
    "rebill_failed",
    "subscription_cancel_requested",
    "subscription_paused",
    "subscription_skipped",
    "subscription_delayed",
    "customer_message_cancellation",
    "customer_message_wismo",
    "customer_message_general",
    "customer_frustrated",
    "customer_payment_method_updated",
    "shipment_delayed",
    "tracking_updated",
    "shipment_exception",
    "shipment_delivered",
    "external_payment_success",
    "workflow_timeout",
    "manual_escalation",
}


class CanonicalEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: uuid4().hex)
    tenant_id: str
    event_type: str
    event_source: str
    entity_type: str
    entity_id: str
    occurred_at: datetime = Field(default_factory=datetime.utcnow)
    payload: dict[str, Any] = Field(default_factory=dict)
