from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


EVENT_TYPES = {
    # Shopify / WISMO
    "order_created",
    "order_updated",
    "order_fulfilled",
    "order_cancelled",
    "customer_created",
    "customer_updated",
    "fulfillment_created",
    "tracking_updated",
    # Workflow runtime
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
