from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from ..models import ActivityLog


def log_activity(
    db: Session,
    tenant_id: UUID,
    initiator: str,
    event_type: str,
    description: str = "",
    patient_reference: str | None = None,
    crm_id: str | None = None,
    api_status: str = "success",
    extra_meta: dict | None = None,
) -> ActivityLog:
    entry = ActivityLog(
        tenant_id=tenant_id,
        initiator=initiator,
        event_type=event_type,
        description=description,
        patient_reference=patient_reference,
        crm_id=crm_id,
        api_status=api_status,
        extra_meta=extra_meta,
    )
    db.add(entry)
    db.commit()
    return entry
