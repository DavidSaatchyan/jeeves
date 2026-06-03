"""Authenticated REST /chat endpoint (FR-5.3)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .auth.deps import get_current_tenant
from .core.communications.webhook_sender import fire_outgoing_webhooks
from .db import get_db
from .models import Tenant
from .agents.service import process_message
from .schemas import ChatIn, ChatOut

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatOut)
async def chat(body: ChatIn, request: Request, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    result = await process_message(
        tenant_id=str(tenant.id),
        customer_id=body.user_id,
        message=body.message,
        channel="web_widget",
        db=db,
    )

    if result.blocked:
        raise HTTPException(400, "Message violates content policy")
    if result.rate_limited:
        raise HTTPException(429, "Rate limit exceeded. Try again later.")

    # Fire outgoing webhooks for configured events
    if result.escalate:
        await fire_outgoing_webhooks(db, tenant.id, body.user_id, "conversation.escalated", {
            "response": result.response,
            "escalated": True,
        })
    await fire_outgoing_webhooks(db, tenant.id, body.user_id, "conversation.ended", {
        "response": result.response,
    })

    return ChatOut(
        response=result.response or "",
        action_called="",
        latency_ms=result.latency_ms,
        escalated=result.escalate,
        resolution="escalated" if result.escalate else "resolved",
    )
