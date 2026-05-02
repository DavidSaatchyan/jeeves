"""Dashboard JSON helpers: stats, logs, billing usage."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from . import billing
from .auth import get_current_tenant
from .db import get_db
from .models import ChatLog, Tenant

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
def stats(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    today = datetime.utcnow().date()
    start = datetime.combine(today, datetime.min.time())
    total_today = (
        db.query(func.count(ChatLog.id))
        .filter(and_(ChatLog.tenant_id == tenant.id, ChatLog.created_at >= start, ChatLog.direction == "incoming"))
        .scalar()
    )
    resolved_today = (
        db.query(func.count(ChatLog.id))
        .filter(
            and_(
                ChatLog.tenant_id == tenant.id,
                ChatLog.created_at >= start,
                ChatLog.direction == "incoming",
                ChatLog.resolution == "resolved",
            )
        )
        .scalar()
    )
    return {
        "dialogs_today": total_today or 0,
        "resolved_today": resolved_today or 0,
        "resolution_rate_today": round((resolved_today or 0) / total_today, 3) if total_today else 0,
        "total_dialogs": tenant.dialogs_used,
        "total_resolved": tenant.resolved_count,
        "overall_resolution_rate": round(tenant.resolved_count / tenant.dialogs_used, 3) if tenant.dialogs_used else 0,
    }


@router.get("/logs")
def logs(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    user_id: str | None = None,
    days: int = 30,
    limit: int = 200,
):
    q = db.query(ChatLog).filter(ChatLog.tenant_id == tenant.id)
    if user_id:
        q = q.filter(ChatLog.user_id == user_id)
    q = q.filter(ChatLog.created_at >= datetime.utcnow() - timedelta(days=days))
    rows = q.order_by(ChatLog.created_at.desc()).limit(limit).all()
    return [
        {
            "id": str(r.id),
            "created_at": r.created_at.isoformat(),
            "user_id": r.user_id,
            "direction": r.direction,
            "message": r.message,
            "response": r.response,
            "resolution": r.resolution,
            "action_called": r.action_called,
            "latency_ms": r.latency_ms,
            "sources": r.sources or [],
        }
        for r in rows
    ]


@router.get("/billing")
def billing_info(tenant: Tenant = Depends(get_current_tenant)):
    return billing.usage(tenant)
