from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ChatLog, ConversationRating, Tenant
from .deps import get_admin_tenant
from .router import router


@router.get("/api/logs")
def api_logs(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    user_id: str | None = None,
    session_id: str | None = None,
    channel: str | None = None,
    resolution: str | None = None,
    days: int = 30,
    limit: int = 50,
    last_id: str | None = None,
):
    limit = min(limit, 200)
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
    if last_id:
        last_log = db.query(ChatLog.created_at).filter(ChatLog.id == last_id).first()
        if last_log:
            q = q.filter(ChatLog.created_at < last_log.created_at)
    rows = q.order_by(ChatLog.created_at.desc()).limit(limit + 1).all()
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:-1]

    session_ids = set(r.session_id for r in rows if r.session_id)
    sessions = {}
    if session_ids:
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

    next_cursor = str(rows[-1].id) if rows and has_more else None
    return {
        "logs": [
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
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@router.post("/api/ratings", status_code=201)
def api_submit_rating(
    body: dict,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
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


@router.get("/api/ratings")
def api_list_ratings(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    user_id: str | None = None,
    days: int = 30,
    limit: int = 50,
    last_id: str | None = None,
):
    limit = min(limit, 200)
    q = db.query(ConversationRating).filter(ConversationRating.tenant_id == tenant.id)
    if user_id:
        q = q.filter(ConversationRating.user_id == user_id)
    q = q.filter(ConversationRating.created_at >= datetime.utcnow() - timedelta(days=days))
    if last_id:
        last_rating = db.query(ConversationRating.created_at).filter(ConversationRating.id == last_id).first()
        if last_rating:
            q = q.filter(ConversationRating.created_at < last_rating.created_at)
    rows = q.order_by(ConversationRating.created_at.desc()).limit(limit + 1).all()
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:-1]

    next_cursor = str(rows[-1].id) if rows and has_more else None
    return {
        "ratings": [
            {
                "id": str(r.id),
                "user_id": r.user_id,
                "message_id": str(r.message_id) if r.message_id else None,
                "rating": r.rating,
                "feedback": r.feedback,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }
