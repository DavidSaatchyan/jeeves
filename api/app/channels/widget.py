"""Web-widget channel: serves `widget.js` loader and accepts unauthenticated
chat requests scoped by data-tenant-id. Outgoing (proactive) messages are
pulled from an inbox endpoint.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ChannelConfig, ChatLog, Conversation, ConversationRating, Message, Tenant
from ..agents.service import process_message
from ..core.compliance.consent import ConsentManager
from ..schemas import ChatOut, WidgetChatIn

router = APIRouter(tags=["widget"])

_WIDGET_JS_PATH = Path("/app/frontend/widget.js")
if not _WIDGET_JS_PATH.exists():
    _WIDGET_JS_PATH = Path(__file__).resolve().parents[3] / "frontend" / "widget.js"


def _get_client_ip(request: Request) -> str:
    return request.headers.get("x-forwarded-for", request.client.host or "unknown").split(",")[0].strip()


def _validate_origin_strict(tenant_id: uuid.UUID, request: Request, db: Session) -> None:
    """Reject if Origin is set and not in tenant's allowed_origins list.
    Unlike the old version, this raises 403 if allowed_origins is configured
    and the origin doesn't match — preventing tenant impersonation.
    """
    origin = request.headers.get("origin", "")
    if not origin:
        raise HTTPException(403, "Origin header required")
    channel_cfg = db.execute(select(ChannelConfig).where(
        ChannelConfig.tenant_id == tenant_id,
        ChannelConfig.channel_type == "web_widget",
    )).scalar_one_or_none()
    if not channel_cfg or not channel_cfg.config:
        return  # no config yet — allow (first-time setup)
    allowed = channel_cfg.config.get("allowed_origins", [])
    if not allowed:
        return  # empty list — allow all
    parsed = urlparse(origin)
    check_origin = f"{parsed.scheme}://{parsed.netloc}"
    if check_origin not in allowed:
        raise HTTPException(403, "Origin not allowed for this tenant")

@router.get("/widget.js")
def widget_js():
    if not _WIDGET_JS_PATH.exists():
        raise HTTPException(404, "widget.js not built")
    return Response(
        content=_WIDGET_JS_PATH.read_text(encoding="utf-8"),
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=60"},
    )


@router.post("/widget/chat", response_model=ChatOut)
async def widget_chat(body: WidgetChatIn, request: Request, db: Session = Depends(get_db)):
    """Widget chat entry point — tenant is identified by tenant_id.

    Security: Origin validation is MANDATORY to prevent tenant impersonation.
    """
    _validate_origin_strict(body.tenant_id, request, db)

    tenant = db.get(Tenant, body.tenant_id)
    if not tenant:
        raise HTTPException(404, "tenant not found")

    channel = body.channel or "web_widget"

    result = await process_message(
        tenant_id=str(tenant.id),
        customer_id=body.user_id,
        message=body.message,
        channel=channel,
        db=db,
        contact_name=body.user_id,
    )

    if result.blocked:
        raise HTTPException(400, "Message violates content policy")
    if result.rate_limited:
        raise HTTPException(429, "Rate limit exceeded. Try again later.")

    # Implied consent capture for new conversations
    if result.is_new_conversation:
        ip = _get_client_ip(request)
        ConsentManager.capture(
            db=db,
            patient_id=None,
            consent_type="data_processing",
            channel="widget",
            consent_text="Implied consent via widget first message",
            tenant_id=tenant.id,
            ip_address=ip,
        )

    return ChatOut(
        response=result.response or "",
        action_called="",
        latency_ms=result.latency_ms,
        escalated=result.escalate,
        resolution="escalated" if result.escalate else "resolved",
    )


@router.get("/widget/inbox")
def widget_inbox(tenant_id: uuid.UUID, user_id: str, viewing: bool = False, request: Request = None, db: Session = Depends(get_db)):
    """Return any undelivered outgoing messages for this user.
    If viewing=True, mark them as delivered (user has the panel open).
    """
    _validate_origin_strict(tenant_id, request, db)

    conv = db.scalar(
        select(Conversation)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.user_id == user_id,
            Conversation.status != "closed",
        )
        .order_by(Conversation.last_message_at.desc())
    )
    if not conv:
        return {"messages": []}

    rows = db.execute(
        select(Message)
        .where(
            Message.conversation_id == conv.id,
            Message.direction == "outgoing",
            Message.delivered.is_(False),
        )
        .order_by(Message.created_at.asc())
    ).scalars().all()
    out = [{"id": str(m.id), "message": m.content, "created_at": m.created_at.isoformat()} for m in rows]
    if viewing:
        for m in rows:
            m.delivered = True
        db.commit()
    return {"messages": out}


@router.post("/widget/rating", status_code=201)
def widget_rating(body: dict, request: Request, db: Session = Depends(get_db)):
    """Submit a conversation rating from the widget."""
    tenant_id = body.get("tenant_id")
    user_id = body.get("user_id", "")
    message_id = body.get("message_id")
    rating = body.get("rating", "thumbs_up")
    feedback = body.get("feedback", "")

    if not tenant_id:
        raise HTTPException(400, "tenant_id required")

    try:
        tid = uuid.UUID(str(tenant_id))
    except ValueError:
        raise HTTPException(400, "invalid tenant_id")

    _validate_origin_strict(tid, request, db)
    tenant = db.execute(select(Tenant).where(Tenant.id == tid)).scalar_one_or_none()
    if not tenant:
        raise HTTPException(404, "tenant not found")

    mid = message_id
    if not mid:
        last = db.execute(select(ChatLog).where(
            ChatLog.tenant_id == tenant.id,
            ChatLog.user_id == user_id,
            ChatLog.channel == body.get("channel", "web_widget"),
            ChatLog.is_user.is_(False),
        ).order_by(ChatLog.created_at.desc())).scalar_one_or_none()
        if last:
            mid = last.session_id

    r = ConversationRating(
        tenant_id=tenant.id,
        user_id=user_id,
        message_id=mid,
        rating=rating,
        feedback=feedback,
    )
    db.add(r)
    db.commit()
    return {"ok": True, "id": str(r.id)}
