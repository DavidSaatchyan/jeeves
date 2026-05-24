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
from ..moderation import moderate
from ..rate_limit import check_rate_limit
from ..schemas import ChatOut, WidgetChatIn
from ..core.ai import simple_llm_response
from ..config import get_settings
from ..shared.inbox_writer import add_message, get_or_create_conversation

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
    channel_cfg = db.query(ChannelConfig).filter(
        ChannelConfig.tenant_id == tenant_id,
        ChannelConfig.channel_type == "web_widget",
    ).first()
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
    ip = _get_client_ip(request)
    if not check_rate_limit("widget", ip):
        raise HTTPException(429, "Rate limit exceeded. Try again later.")

    flagged, category = moderate(body.message)
    if flagged:
        raise HTTPException(400, "Message violates content policy")

    _validate_origin_strict(body.tenant_id, request, db)

    tenant = db.get(Tenant, body.tenant_id)
    if not tenant:
        raise HTTPException(404, "tenant not found")

    session_id = uuid.uuid4()

    log = ChatLog(
        tenant_id=tenant.id,
        user_id=body.user_id,
        direction="incoming",
        message=body.message,
        extra_fields=body.extra_fields or {},
        session_id=session_id,
    )
    db.add(log)

    channel = body.channel or "web_widget"
    conv = get_or_create_conversation(db, tenant.id, body.user_id, channel=channel, user_display_name=body.user_id)
    add_message(db, conv, "incoming", body.message, sender_type="customer")
    db.commit()

    # Load conversation history for LLM context
    from ..core.memory import get_conversation_history
    history = get_conversation_history(
        tenant_id=str(tenant.id),
        customer_id=body.user_id,
        db=db,
    )

    # Intent classification — decide whether this is an order tracking inquiry,
    # a knowledge base question, or general chat
    from ..core.ai.intent_classifier import classify_intent
    intent = await classify_intent(body.message, str(tenant.id), history=history)

    if intent == "wismo":
        # Order tracking inquiry → route to WISMO workflow
        from uuid import UUID
        from ..core.events.schemas import CanonicalEvent
        from ..core.workflows.registry import route_event

        ev = CanonicalEvent(
            event_type="intent:wismo",
            event_source="widget_chat",
            tenant_id=str(tenant.id),
            entity_type="chat",
            entity_id=str(session_id),
            payload={
                "customer_id": body.user_id,
                "message": body.message,
                "history": history,
            },
        )
        await route_event(ev, db)

        latest = (
            db.query(ChatLog)
            .filter(
                ChatLog.tenant_id == tenant.id,
                ChatLog.user_id == body.user_id,
                ChatLog.direction == "outgoing",
                ChatLog.delivered == False,
            )
            .order_by(ChatLog.created_at.desc())
            .first()
        )
        response_text = (
            latest.response
            if latest
            else "I'm looking up your order information right now. I'll send you a notification as soon as I have an update!"
        )
        result = {"response": response_text, "latency_ms": 0, "escalated": False}

    elif intent == "general":
        # Simple greeting / small talk — no RAG needed
        result = await simple_llm_response(tenant.id, body.message, conversation_history=history)

    else:
        # kb_query — RAG search + LLM response (existing flow)
        import asyncio
        try:
            from ..core.ai.generator import translate_query
            query = await translate_query(body.message)
            from .. import rag
            chunks = await asyncio.to_thread(rag.search, tenant.id, query)
        except Exception:
            chunks = []
        context = "\n\n".join(c["text"] for c in chunks) if chunks else ""
        if context:
            system = (
                "You are a support agent. Answer the user's question based ONLY on the context below. "
                "If the context doesn't contain enough information, say you don't have that information "
                "in your knowledge base and offer to connect with a specialist."
            )
            if history:
                history_str = "\n".join(f"- {e['role']}: {e['content']}" for e in history)
                system += f"\n\nConversation history:\n{history_str}"
            system += f"\n\nContext:\n{context}"
        else:
            system = (
                "You are a support agent. You do not have the information to answer this question "
                "in your knowledge base. Respond that this information is not available and offer to "
                "connect the user with a specialist."
            )
            if history:
                history_str = "\n".join(f"- {e['role']}: {e['content']}" for e in history)
                system += f"\n\nConversation history:\n{history_str}"

        result = await simple_llm_response(tenant.id, body.message, system_override=system)

    log.response = result["response"]
    log.resolution = "resolved"
    log.latency_ms = result["latency_ms"]
    log.session_id = session_id
    log.channel = channel
    if log.channel != "test_widget":
        tenant.dialogs_used += 1
        tenant.resolved_count += 1
    if intent != "wismo":
        add_message(db, conv, "outgoing", result["response"], sender_type="bot")
    db.commit()

    return ChatOut(
        response=result["response"],
        action_called="",
        latency_ms=result["latency_ms"],
        escalated=False,
        resolution="resolved",
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
            Message.delivered == False,
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
    tenant = db.query(Tenant).filter(Tenant.id == tid).first()
    if not tenant:
        raise HTTPException(404, "tenant not found")

    mid = message_id
    if not mid:
        last = db.query(ChatLog).filter(
            ChatLog.tenant_id == tenant.id,
            ChatLog.user_id == user_id,
            ChatLog.channel == body.get("channel", "web_widget"),
            ChatLog.is_user == False,
        ).order_by(ChatLog.created_at.desc()).first()
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
