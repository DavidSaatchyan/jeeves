from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


EVENT_TYPES: set[str] = {
    # Workflow runtime
    "workflow_timeout",
    "manual_escalation",
    # Medical event types (Phase 5)
    "appointment_requested",
    "patient_message_received",
    # Marketing & Follow-up (Phase 6)
    "campaign_scheduled",
    "campaign_event",
    "followup_due",
    "visit_completed",
    "patient_responded",
    "nurture_due",
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
