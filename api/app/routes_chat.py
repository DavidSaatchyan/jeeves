"""Authenticated REST /chat endpoint (FR-5.3)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from . import agent, billing
from .auth import get_current_tenant
from .db import get_db
from .models import ChatLog, Tenant
from .moderation import moderate
from .rate_limit import check_rate_limit
from .schemas import ChatIn, ChatOut

router = APIRouter(tags=["chat"])


def _get_client_ip(request: Request) -> str:
    return request.headers.get("x-forwarded-for", request.client.host or "unknown").split(",")[0].strip()


def _enqueue_outgoing_webhooks(db: Session, tenant_id, user_id: str, event: str, result: dict):
    """Enqueue send_outgoing_webhook Celery task for configured events."""
    try:
        from tasks import send_outgoing_webhook
    except ImportError:
        return

    from .models import WebhookConfig
    cfg = db.query(WebhookConfig).filter(
        WebhookConfig.tenant_id == tenant_id,
        WebhookConfig.enabled == True,  # noqa: E712
    ).first()
    if not cfg or not cfg.events:
        return

    events = cfg.events if isinstance(cfg.events, list) else []
    if event not in events:
        return

    payload = {
        "tenant_id": str(tenant_id),
        "user_id": user_id,
        "event": event,
        "response": result.get("response", ""),
        "action_called": result.get("action_called"),
        "escalated": result.get("escalated", False),
        "session_id": result.get("session_id"),
    }
    try:
        send_outgoing_webhook.delay(str(tenant_id), event, payload)
    except Exception as e:
        print(f"[chat] webhook enqueue failed: {e}", flush=True)


def _enqueue_writeback(db: Session, tenant_id, session_id: str):
    """Enqueue writeback_conversation Celery task on conversation end."""
    try:
        from tasks import writeback_conversation
    except ImportError:
        return

    from .models import WriteBackConfig
    cfg = db.query(WriteBackConfig).filter(
        WriteBackConfig.tenant_id == tenant_id,
    ).first()
    if not cfg or cfg.type == "off":
        return

    try:
        writeback_conversation.delay(str(tenant_id), session_id)
    except Exception as e:
        print(f"[chat] writeback enqueue failed: {e}", flush=True)


@router.post("/chat", response_model=ChatOut)
async def chat(body: ChatIn, request: Request, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    ip = _get_client_ip(request)
    if not check_rate_limit("chat", ip):
        raise HTTPException(429, "Rate limit exceeded. Try again later.")

    flagged, category = moderate(body.message)
    if flagged:
        raise HTTPException(400, "Message violates content policy")

    billing.enforce(tenant)

    session_id = uuid.uuid4()

    log = ChatLog(
        tenant_id=tenant.id,
        user_id=body.user_id,
        direction="incoming",
        message=body.message,
        session_id=session_id,
    )
    db.add(log)
    db.commit()

    result = await agent.run(db, tenant.id, body.user_id, body.message, session_id=session_id)

    log.response = result["response"]
    log.resolution = "escalated" if result["escalated"] else "resolved"
    log.action_called = result["action_called"]
    log.latency_ms = result["latency_ms"]
    log.sources = result.get("sources") or []
    log.session_id = result.get("session_id")
    tenant.dialogs_used += 1
    if not result["escalated"]:
        tenant.resolved_count += 1
    db.commit()

    # Enqueue outgoing webhooks for configured events
    if result.get("action_called"):
        _enqueue_outgoing_webhooks(db, tenant.id, body.user_id, "action.called", result)
    if result.get("escalated"):
        _enqueue_outgoing_webhooks(db, tenant.id, body.user_id, "conversation.escalated", result)
    _enqueue_outgoing_webhooks(db, tenant.id, body.user_id, "conversation.ended", result)

    # Enqueue writeback on conversation end
    _enqueue_writeback(db, tenant.id, result.get("session_id", str(session_id)))

    return ChatOut(
        response=result["response"],
        action_called=result["action_called"],
        latency_ms=result["latency_ms"],
        escalated=result.get("escalated", False),
        resolution="escalated" if result.get("escalated") else "resolved",
    )
