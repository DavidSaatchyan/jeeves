from __future__ import annotations

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


from ..compliance.audit import record_audit_event


def record_transition(
    db: Session,
    workflow_id: UUID,
    workflow_type: str,
    from_state: str,
    to_state: str,
    trigger_event: str,
    decision_reason: str = "",
    policy_snapshot: dict | None = None,
) -> None:
    db.execute(
        text("""
            INSERT INTO workflow_transitions (id, workflow_id, from_state, to_state, trigger_event,
                decision_reason, policy_snapshot, created_at)
            VALUES (:id, :wid, :from_s, :to_s, :trigger, :reason, :policy, :now)
        """),
        {
            "id": uuid.uuid4(),
            "wid": workflow_id,
            "from_s": from_state,
            "to_s": to_state,
            "trigger": trigger_event,
            "reason": decision_reason,
            "policy": policy_snapshot or {},
            "now": datetime.utcnow(),
        },
    )

    db.execute(
        text("UPDATE workflows SET current_state = :state, updated_at = :now WHERE id = :id"),
        {"state": to_state, "now": datetime.utcnow(), "id": workflow_id},
    )


def record_timeline_event(
    db: Session,
    event_type: str,
    entity_type: str,
    entity_id: str,
    tenant_id: str,
    payload: dict | None = None,
) -> None:
    db.execute(
        text("""
            INSERT INTO timeline_events (id, tenant_id, entity_type, entity_id, event_type, payload, created_at)
            VALUES (:id, :tid, :et, :eid, :evt, :pl, :now)
        """),
        {
            "id": uuid.uuid4(),
            "tid": tenant_id,
            "et": entity_type,
            "eid": entity_id,
            "evt": event_type,
            "pl": payload or {},
            "now": datetime.utcnow(),
        },
    )


def record_compliance_event(
    db: Session,
    tenant_id: UUID,
    action: str,
    actor_type: str,
    actor_id: str,
    patient_id: UUID | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
) -> None:
    record_audit_event(
        db=db,
        tenant_id=tenant_id,
        action=action,
        actor_type=actor_type,
        actor_id=actor_id,
        patient_id=patient_id,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
    )
