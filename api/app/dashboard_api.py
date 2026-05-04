"""Dashboard JSON helpers: stats, logs, billing usage."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, text
from sqlalchemy.orm import Session

from . import billing
from .auth import get_current_tenant
from .db import get_db
from .models import AgentTool, ChannelConfig, ChatLog, CRMConnection, FileRecord, NativeConnector, Tenant

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
def stats(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    today = datetime.utcnow().date()
    start = datetime.combine(today, datetime.min.time())
    week_start = (datetime.utcnow() - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)

    total_today = (
        db.query(func.count(ChatLog.id))
        .filter(and_(ChatLog.tenant_id == tenant.id, ChatLog.created_at >= start))
        .scalar()
    )
    resolved_today = (
        db.query(func.count(ChatLog.id))
        .filter(and_(ChatLog.tenant_id == tenant.id, ChatLog.created_at >= start, ChatLog.resolution == "resolved"))
        .scalar()
    )
    total_week = (
        db.query(func.count(ChatLog.id))
        .filter(and_(ChatLog.tenant_id == tenant.id, ChatLog.created_at >= week_start))
        .scalar()
    )
    resolved_week = (
        db.query(func.count(ChatLog.id))
        .filter(and_(ChatLog.tenant_id == tenant.id, ChatLog.created_at >= week_start, ChatLog.resolution == "resolved"))
        .scalar()
    )
    avg_latency = (
        db.query(func.avg(ChatLog.latency_ms))
        .filter(and_(ChatLog.tenant_id == tenant.id, ChatLog.created_at >= week_start, ChatLog.latency_ms.isnot(None)))
        .scalar()
    )
    escalated_week = (
        db.query(func.count(ChatLog.id))
        .filter(and_(ChatLog.tenant_id == tenant.id, ChatLog.created_at >= week_start, ChatLog.resolution == "escalated"))
        .scalar()
    )
    return {
        "dialogs_today": total_today or 0,
        "resolved_today": resolved_today or 0,
        "dialogs_week": total_week or 0,
        "resolved_week": resolved_week or 0,
        "resolution_rate_week": round((resolved_week or 0) / total_week, 3) if total_week else 0,
        "avg_latency_ms": round(avg_latency) if avg_latency else 0,
        "escalated_week": escalated_week or 0,
    }


@router.get("/trend")
def trend(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db), days: int = 7):
    """Daily dialog counts for the last N days with resolution breakdown."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    # Get total counts per day
    totals = (
        db.query(func.date(ChatLog.created_at).label("day"), func.count(ChatLog.id).label("total"))
        .filter(and_(ChatLog.tenant_id == tenant.id, ChatLog.created_at >= cutoff))
        .group_by(func.date(ChatLog.created_at))
        .all()
    )

    # Get resolved per day
    resolved = (
        db.query(func.date(ChatLog.created_at).label("day"), func.count(ChatLog.id).label("resolved"))
        .filter(and_(ChatLog.tenant_id == tenant.id, ChatLog.created_at >= cutoff, ChatLog.resolution == "resolved"))
        .group_by(func.date(ChatLog.created_at))
        .all()
    )

    # Get escalated per day
    escalated = (
        db.query(func.date(ChatLog.created_at).label("day"), func.count(ChatLog.id).label("escalated"))
        .filter(and_(ChatLog.tenant_id == tenant.id, ChatLog.created_at >= cutoff, ChatLog.resolution == "escalated"))
        .group_by(func.date(ChatLog.created_at))
        .all()
    )

    # Build day-indexed maps
    total_map = {str(r.day): r.total for r in totals}
    resolved_map = {str(r.day): r.resolved for r in resolved}
    escalated_map = {str(r.day): r.escalated for r in escalated}

    result = []
    for i in range(days):
        d = (datetime.utcnow() - timedelta(days=days - 1 - i)).date()
        ds = str(d)
        result.append({
            "date": ds,
            "total": total_map.get(ds, 0),
            "resolved": resolved_map.get(ds, 0),
            "escalated": escalated_map.get(ds, 0),
        })
    return result


@router.get("/channels-breakdown")
def channels_breakdown(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    """Dialog counts per channel for the last 7 days."""
    cutoff = datetime.utcnow() - timedelta(days=7)
    rows = (
        db.query(ChatLog.channel, func.count(ChatLog.id))
        .filter(and_(ChatLog.tenant_id == tenant.id, ChatLog.created_at >= cutoff))
        .group_by(ChatLog.channel)
        .all()
    )
    return [{"channel": r[0], "count": r[1]} for r in rows]


@router.get("/hourly")
def hourly(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    """Dialogs by hour of day (0-23) for the last 7 days."""
    cutoff = datetime.utcnow() - timedelta(days=7)
    rows = (
        db.query(func.extract("hour", ChatLog.created_at).label("h"), func.count(ChatLog.id))
        .filter(and_(ChatLog.tenant_id == tenant.id, ChatLog.created_at >= cutoff))
        .group_by("h")
        .order_by("h")
        .all()
    )
    result = [0] * 24
    for r in rows:
        h = int(r[0])
        if 0 <= h < 24:
            result[h] = r[1]
    return result


@router.get("/setup-status")
def setup_status(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    """Returns which setup steps are completed."""
    kb_ready = db.query(FileRecord).filter(
        and_(FileRecord.tenant_id == tenant.id, FileRecord.status == "ready")
    ).first() is not None

    active_channels = db.query(ChannelConfig).filter(
        and_(ChannelConfig.tenant_id == tenant.id, ChannelConfig.status == "active")
    ).all()

    has_crm = db.query(CRMConnection).filter(CRMConnection.tenant_id == tenant.id).first() is not None
    has_tools = db.query(AgentTool).filter(and_(AgentTool.tenant_id == tenant.id, AgentTool.enabled == True)).first() is not None
    has_native = db.query(NativeConnector).filter(and_(NativeConnector.tenant_id == tenant.id, NativeConnector.status == "connected")).first() is not None

    return {
        "knowledge_uploaded": kb_ready,
        "channels_active": [c.channel_type for c in active_channels],
        "crm_configured": has_crm,
        "tools_enabled": has_tools,
        "native_integrations": has_native,
        "setup_complete": kb_ready and len(active_channels) > 0,
    }


@router.get("/recent-unresolved")
def recent_unresolved(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db), limit: int = 10):
    """Recent conversations that were not resolved."""
    rows = (
        db.query(ChatLog)
        .filter(and_(
            ChatLog.tenant_id == tenant.id,
            ChatLog.resolution == "escalated",
        ))
        .order_by(ChatLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": str(r.id),
            "created_at": r.created_at.isoformat(),
            "user_id": r.user_id,
            "message": (r.message or "")[:200],
            "response": (r.response or "")[:200],
            "channel": r.channel,
            "latency_ms": r.latency_ms,
        }
        for r in rows
    ]


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
