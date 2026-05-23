from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

WORKFLOW_REGISTRY: dict[str, type] = {}


def register_workflow(workflow_type: str, cls: type) -> None:
    WORKFLOW_REGISTRY[workflow_type] = cls
    logger.info("registered workflow type: %s \u2192 %s", workflow_type, cls.__name__)


def get_workflow_class(workflow_type: str) -> type | None:
    return WORKFLOW_REGISTRY.get(workflow_type)

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
