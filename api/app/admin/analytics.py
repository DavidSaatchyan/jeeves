from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db

from ..models import Communication, Tenant, Workflow
from .deps import get_admin_tenant
from .router import router


@router.get("/api/analytics")
def api_analytics(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    workflows = (
        db.query(Workflow)
        .filter(Workflow.tenant_id == tenant.id, Workflow.started_at >= thirty_days_ago)
        .all()
    )

    total = len(workflows)
    recovered = sum(1 for w in workflows if w.current_state in ("RECOVERED", "RETAINED", "RESOLVED"))
    failed = sum(1 for w in workflows if w.current_state in ("FAILED", "CANCELLED"))
    active = sum(1 for w in workflows if w.status in ("active", "paused"))

    esc_count = 0

    comms_count = (
        db.query(func.count(Communication.id))
        .filter(Communication.tenant_id == tenant.id, Communication.created_at >= thirty_days_ago)
        .scalar()
        or 0
    )

    return {
        "total_workflows": total,
        "active_workflows": active,
        "recovered": recovered,
        "failed": failed,
        "escalations": esc_count,
        "communications_sent": comms_count,
    }
