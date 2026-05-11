from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from ..events.schemas import CanonicalEvent
from ..policies.engine import PolicyEngine

logger = logging.getLogger(__name__)

WORKFLOW_REGISTRY: dict[str, type] = {}


def register_workflow(workflow_type: str, cls: type) -> None:
    WORKFLOW_REGISTRY[workflow_type] = cls
    logger.info("registered workflow type: %s → %s", workflow_type, cls.__name__)


def get_workflow_class(workflow_type: str) -> type | None:
    return WORKFLOW_REGISTRY.get(workflow_type)


async def route_event(event: CanonicalEvent, db: Session) -> None:
    from .runtime import Workflow

    event_type = event.event_type
    entity_id = event.entity_id

    type_to_workflow = {
        "payment_failed": "payment_recovery",
        "invoice_payment_failed": "payment_recovery",
        "rebill_failed": "payment_recovery",
    }

    workflow_type = type_to_workflow.get(event_type)
    if not workflow_type:
        return

    cls = get_workflow_class(workflow_type)
    if not cls:
        logger.warning("no workflow class registered for type: %s", workflow_type)
        return

    try:
        inst = _find_or_create_workflow(db, event, workflow_type, cls)
        if inst is None:
            return
        await inst.handle_event(event, db)
    except Exception as e:
        logger.exception("workflow routing failed: %s", e)


def _find_or_create_workflow(
    db: Session, event: CanonicalEvent, workflow_type: str, cls: type
) -> Any | None:
    from sqlalchemy import text

    tenant_id = event.tenant_id
    customer_id = event.payload.get("customer_id", event.entity_id)

    existing = db.execute(
        text("""
            SELECT id, current_state, status FROM workflows
            WHERE tenant_id = :tid AND workflow_type = :wt AND customer_id = :cid
              AND status IN ('active', 'paused')
            LIMIT 1
        """),
        {"tid": tenant_id, "wt": workflow_type, "cid": customer_id},
    ).first()

    engine = PolicyEngine(tenant_id, db=db)

    if existing:
        return cls(
            workflow_id=UUID(existing[0]),
            tenant_id=UUID(tenant_id),
            customer_id=customer_id,
            workflow_type=workflow_type,
            current_state=existing[1],
            status=existing[2],
            policy_engine=engine,
        )

    import uuid as _uuid
    from datetime import datetime, timedelta

    wid = _uuid.uuid4()
    now = datetime.utcnow()
    expiration = now + timedelta(days=7)

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
            "state": "DETECTED",
            "now": now,
            "exp": expiration,
        },
    )
    db.commit()

    return cls(
        workflow_id=wid,
        tenant_id=UUID(tenant_id),
        customer_id=customer_id,
        workflow_type=workflow_type,
        current_state="DETECTED",
        status="active",
        started_at=now,
        policy_engine=engine,
    )
