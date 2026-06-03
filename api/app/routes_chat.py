"""Authenticated REST /chat endpoint (FR-5.3)."""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .auth.deps import get_current_tenant
from .core.ai import simple_llm_response
from .core.communications.webhook_sender import fire_outgoing_webhooks
from .db import get_db
from .models import ChatLog, Tenant
from .shared.moderation import moderate
from .shared.rate_limit import check_rate_limit
from .schemas import ChatIn, ChatOut
from .shared.inbox_writer import add_message, get_or_create_conversation

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


def _get_client_ip(request: Request) -> str:
    return request.headers.get("x-forwarded-for", request.client.host or "unknown").split(",")[0].strip()


@router.post("/chat", response_model=ChatOut)
async def chat(body: ChatIn, request: Request, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    ip = _get_client_ip(request)
    if not check_rate_limit("chat", ip):
        raise HTTPException(429, "Rate limit exceeded. Try again later.")

    flagged, category = moderate(body.message)
    if flagged:
        raise HTTPException(400, "Message violates content policy")

    session_id = uuid.uuid4()

    log = ChatLog(
        tenant_id=tenant.id,
        user_id=body.user_id,
        direction="incoming",
        message=body.message,
        session_id=session_id,
    )
    db.add(log)

    conv = get_or_create_conversation(db, tenant.id, body.user_id, channel="web_widget", user_display_name=body.user_id)
    add_message(db, conv, "incoming", body.message, sender_type="customer")
    db.commit()

    result = await simple_llm_response(tenant.id, body.message)

    log.response = result["response"]
    log.resolution = "resolved"
    log.latency_ms = result["latency_ms"]
    log.session_id = session_id
    tenant.dialogs_used += 1
    tenant.resolved_count += 1
    add_message(db, conv, "outgoing", result["response"], sender_type="bot")
    db.commit()

    # Fire outgoing webhooks for configured events
    if result.get("action_called"):
        await fire_outgoing_webhooks(db, tenant.id, body.user_id, "action.called", result)
    if result.get("escalated"):
        await fire_outgoing_webhooks(db, tenant.id, body.user_id, "conversation.escalated", result)
    await fire_outgoing_webhooks(db, tenant.id, body.user_id, "conversation.ended", result)

    return ChatOut(
        response=result["response"],
        action_called="",
        latency_ms=result["latency_ms"],
        escalated=False,
        resolution="resolved",
    )
