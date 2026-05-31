from __future__ import annotations

import logging
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..events.schemas import CanonicalEvent

logger = logging.getLogger(__name__)

WORKFLOW_REGISTRY: dict[str, type] = {}


def register_workflow(workflow_type: str, cls: type) -> None:
    WORKFLOW_REGISTRY[workflow_type] = cls
    logger.info("registered workflow type: %s \u2192 %s", workflow_type, cls.__name__)


def get_workflow_class(workflow_type: str) -> type | None:
    return WORKFLOW_REGISTRY.get(workflow_type)


async def route_event(event: CanonicalEvent, db: Session) -> None:
    """Route a canonical event to the appropriate workflow.

    Phase 1 stub — medical workflow routing added in Phase 5.
    """
    wf_type = event.event_source
    cls = get_workflow_class(wf_type)
    if cls is None:
        logger.debug("no workflow handler for event type: %s", event.event_type)
        return

    payload = event.payload or {}
    customer_id = str(payload.get("customer_id") or payload.get("patient_id") or "")
    if not customer_id:
        logger.warning("cannot route event %s: missing customer_id/patient_id", event.event_id)
        return

    tenant_id = UUID(event.tenant_id)
    workflow = _load_or_create_workflow(db, cls, tenant_id, customer_id, wf_type, payload)
    if workflow is None:
        return

    await workflow.handle_event(event, db)


def _load_or_create_workflow(
    db: Session, cls: type, tenant_id: UUID, customer_id: str, workflow_type: str, payload: dict,
) -> object | None:
    existing = db.execute(
        text("""
            SELECT id, current_state, status, started_at
            FROM workflows
            WHERE tenant_id = :tid AND customer_id = :cid AND workflow_type = :wtype
              AND status IN ('active', 'paused')
            ORDER BY started_at DESC
            LIMIT 1
        """),
        {"tid": tenant_id, "cid": customer_id, "wtype": workflow_type},
    ).mappings().first()

    if existing is not None:
        return cls(
            workflow_id=existing["id"],
            tenant_id=tenant_id,
            customer_id=customer_id,
            workflow_type=workflow_type,
            current_state=existing["current_state"],
            status=existing["status"],
            started_at=existing["started_at"],
        )

    wid = uuid4()
    now = datetime.utcnow()
    expiration = now + timedelta(days=30)

    db.execute(
        text("""
            INSERT INTO workflows (id, tenant_id, customer_id, workflow_type, current_state, status, started_at, expiration_at)
            VALUES (:id, :tid, :cid, :wt, :state, 'active', :now, :exp)
        """),
        {
            "id": wid,
            "tid": tenant_id,
            "cid": customer_id,
            "wt": workflow_type,
            "state": "STARTED",
            "now": now,
            "exp": expiration,
        },
    )
    db.commit()

    return cls(
        workflow_id=wid,
        tenant_id=tenant_id,
        customer_id=customer_id,
        workflow_type=workflow_type,
        current_state="STARTED",
        status="active",
        started_at=now,
    )
