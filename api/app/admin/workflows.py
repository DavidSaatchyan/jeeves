from __future__ import annotations

import uuid as uuid_mod

from fastapi import Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db

from ..models import Tenant, TimelineEvent, Workflow
from .deps import get_admin_tenant
from .router import router


@router.get("/api/workflows")
def api_workflows(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    workflow_type: str | None = Query(None, alias="type"),
    status: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    q = select(Workflow).where(Workflow.tenant_id == tenant.id)
    if workflow_type:
        q = q.filter(Workflow.workflow_type == workflow_type)
    if status:
        q = q.filter(Workflow.status == status)
    total = q.count()
    rows = q.order_by(Workflow.started_at.desc()).offset(offset).limit(limit).all()
    return {
        "workflows": [
            {
                "id": str(w.id),
                "workflow_type": w.workflow_type,
                "customer_id": w.customer_id,
                "current_state": w.current_state,
                "status": w.status,
                "started_at": w.started_at.isoformat() if w.started_at else None,
                "updated_at": w.updated_at.isoformat() if w.updated_at else None,
                "completed_at": w.completed_at.isoformat() if w.completed_at else None,
                "priority": w.priority,
            }
            for w in rows
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/api/workflows/{workflow_id}/timeline")
def api_workflow_timeline(
    workflow_id: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    try:
        uuid_mod.UUID(workflow_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid workflow ID")
    events = (
        db.execute(select(TimelineEvent).where(
            TimelineEvent.tenant_id == tenant.id,
            TimelineEvent.entity_type == "workflow",
            TimelineEvent.entity_id == workflow_id,
        )).scalars()
        .order_by(TimelineEvent.created_at.desc())
        .limit(100)
        .all()
    )
    return {
        "events": [
            {
                "id": str(e.id),
                "event_type": e.event_type,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "payload": e.payload,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ]
    }


