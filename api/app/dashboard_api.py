"""Dashboard JSON helpers: stats, logs, billing usage."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, text, Integer
from sqlalchemy.orm import Session

from . import billing
from .auth import get_current_tenant
from .db import get_db
from .models import AgentTool, ChannelConfig, ChatLog, ConversationRating, CRMConnection, FileRecord, NativeConnector, Tenant

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
def stats(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    today = datetime.utcnow().date()
    start = datetime.combine(today, datetime.min.time())
    week_start = (datetime.utcnow() - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)

    # Two queries (today + week) with conditional SUM for breakdown — much faster than 5 separate queries
    def _window(cutoff):
        row = db.query(
            func.count(ChatLog.id).label("dialogs"),
            func.sum(func.cast(ChatLog.resolution == "resolved", Integer)).label("resolved"),
            func.sum(func.cast(ChatLog.resolution == "escalated", Integer)).label("escalated"),
            func.avg(ChatLog.latency_ms).label("avg_latency"),
        ).filter(
            and_(
                ChatLog.tenant_id == tenant.id,
                ChatLog.created_at >= cutoff,
                ChatLog.channel != "test_widget",
            )
        ).first()
        return row

    w = _window(week_start)
    t = _window(start)

    dialogs_week = w.dialogs or 0
    resolved_week = int(w.resolved or 0)
    escalated_week = int(w.escalated or 0)

    return {
        "dialogs_today": t.dialogs or 0,
        "resolved_today": int(t.resolved or 0),
        "dialogs_week": dialogs_week,
        "resolved_week": resolved_week,
        "resolution_rate_week": round(resolved_week / dialogs_week, 3) if dialogs_week else 0,
        "avg_latency_ms": round(w.avg_latency) if w.avg_latency else 0,
        "escalated_week": escalated_week,
    }


@router.get("/trend")
def trend(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db), days: int = 7):
    """Daily dialog counts for the last N days with resolution breakdown — single query."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    rows = (
        db.query(
            func.date(ChatLog.created_at).label("day"),
            func.count(ChatLog.id).label("total"),
            func.sum(func.cast(ChatLog.resolution == "resolved", Integer)).label("resolved"),
            func.sum(func.cast(ChatLog.resolution == "escalated", Integer)).label("escalated"),
        )
        .filter(and_(ChatLog.tenant_id == tenant.id, ChatLog.created_at >= cutoff, ChatLog.channel != "test_widget"))
        .group_by(func.date(ChatLog.created_at))
        .all()
    )

    total_map = {str(r.day): r.total for r in rows}
    resolved_map = {str(r.day): int(r.resolved or 0) for r in rows}
    escalated_map = {str(r.day): int(r.escalated or 0) for r in rows}

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
        .filter(and_(ChatLog.tenant_id == tenant.id, ChatLog.created_at >= cutoff, ChatLog.channel != "test_widget"))
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
        .filter(and_(ChatLog.tenant_id == tenant.id, ChatLog.created_at >= cutoff, ChatLog.channel != "test_widget"))
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
            ChatLog.channel != "test_widget",
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
    session_id: str | None = None,
    channel: str | None = None,
    resolution: str | None = None,
    days: int = 30,
    limit: int = 500,
):
    q = db.query(ChatLog).filter(ChatLog.tenant_id == tenant.id)
    if user_id:
        q = q.filter(ChatLog.user_id == user_id)
    if session_id:
        q = q.filter(ChatLog.session_id == session_id)
    if channel:
        q = q.filter(ChatLog.channel == channel)
    if resolution:
        q = q.filter(ChatLog.resolution == resolution)
    q = q.filter(ChatLog.created_at >= datetime.utcnow() - timedelta(days=days))
    rows = q.order_by(ChatLog.created_at.desc()).limit(limit).all()

    # Aggregate session info
    session_ids = set(r.session_id for r in rows if r.session_id)
    sessions = {}
    if session_ids:
        from sqlalchemy import func
        session_rows = (
            db.query(
                ChatLog.session_id,
                func.count(ChatLog.id).label("turns"),
                func.min(ChatLog.created_at).label("started_at"),
                func.max(ChatLog.created_at).label("last_at"),
            )
            .filter(ChatLog.session_id.in_(session_ids))
            .group_by(ChatLog.session_id)
            .all()
        )
        for sr in session_rows:
            sessions[str(sr.session_id)] = {
                "turns": sr.turns,
                "started_at": sr.started_at.isoformat() if sr.started_at else None,
                "last_at": sr.last_at.isoformat() if sr.last_at else None,
            }

    return [
        {
            "id": str(r.id),
            "session_id": str(r.session_id) if r.session_id else None,
            "created_at": r.created_at.isoformat(),
            "user_id": r.user_id,
            "direction": r.direction,
            "message": r.message,
            "response": r.response,
            "resolution": r.resolution,
            "action_called": r.action_called,
            "latency_ms": r.latency_ms,
            "delivered": r.delivered,
            "sources": r.sources or [],
            "channel": r.channel,
            "extra_fields": r.extra_fields or {},
            "session_info": sessions.get(str(r.session_id)) if r.session_id else None,
        }
        for r in rows
    ]


@router.get("/billing")
def billing_info(tenant: Tenant = Depends(get_current_tenant)):
    return billing.usage(tenant)


@router.post("/ratings", status_code=201)
def submit_rating(
    body: dict,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Submit a conversation rating."""
    rating = ConversationRating(
        tenant_id=tenant.id,
        user_id=body.get("user_id", ""),
        message_id=body.get("message_id"),
        rating=body.get("rating", "thumbs_up"),
        feedback=body.get("feedback", ""),
    )
    db.add(rating)
    db.commit()
    return {"ok": True, "id": str(rating.id)}


@router.get("/ratings")
def list_ratings(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    user_id: str | None = None,
    days: int = 30,
):
    """List conversation ratings."""
    q = db.query(ConversationRating).filter(ConversationRating.tenant_id == tenant.id)
    if user_id:
        q = q.filter(ConversationRating.user_id == user_id)
    q = q.filter(ConversationRating.created_at >= datetime.utcnow() - timedelta(days=days))
    rows = q.order_by(ConversationRating.created_at.desc()).all()
    return [
        {
            "id": str(r.id),
            "user_id": r.user_id,
            "message_id": str(r.message_id) if r.message_id else None,
            "rating": r.rating,
            "feedback": r.feedback,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
