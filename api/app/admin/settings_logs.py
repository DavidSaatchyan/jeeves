from __future__ import annotations

from datetime import datetime

from fastapi import Depends, Query, Request
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ActivityLog, Tenant, TeamMember
from .deps import get_admin_tenant, require_role
from .router import router


@router.get("/api/settings/logs")
def api_activity_logs(
    request: Request,
    patient: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    _: TeamMember = Depends(require_role("owner", "manager")),
):
    q = select(ActivityLog).where(ActivityLog.tenant_id == tenant.id)

    if patient:
        q = q.where(ActivityLog.patient_reference.ilike(f"%{patient}%"))
    if event_type:
        q = q.where(ActivityLog.event_type == event_type)
    if status:
        q = q.where(ActivityLog.api_status == status)
    if from_date:
        try:
            dt = datetime.fromisoformat(from_date)
            q = q.where(ActivityLog.created_at >= dt)
        except ValueError:
            pass
    if to_date:
        try:
            dt = datetime.fromisoformat(to_date)
            q = q.where(ActivityLog.created_at <= dt)
        except ValueError:
            pass

    count_q = select(func.count()).select_from(q.subquery())
    total = db.execute(count_q).scalar() or 0

    q = q.order_by(desc(ActivityLog.created_at))
    q = q.offset((page - 1) * per_page).limit(per_page)
    rows = db.execute(q).scalars().all()

    return {
        "logs": [
            {
                "id": str(r.id),
                "initiator": r.initiator,
                "event_type": r.event_type,
                "description": r.description,
                "patient_reference": r.patient_reference,
                "crm_id": r.crm_id,
                "api_status": r.api_status,
                "extra_meta": r.extra_meta,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page),
    }
