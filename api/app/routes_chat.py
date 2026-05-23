"""Authenticated REST /chat endpoint (FR-5.3)."""
from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .auth import get_current_tenant
from .db import get_db
from .models import ChatLog, Tenant, WebhookConfig
from .moderation import moderate
from .rate_limit import check_rate_limit
from .schemas import ChatIn, ChatOut

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


async def _simple_llm_response(tenant_id, message: str, system_override=None, conversation_history: list[dict] | None = None) -> dict:
    """Direct LLM call without agent tool loop (v2 replacement).
    If system_override is provided, prepend a system message with RAG context.
    """
    import time
    from .config import get_settings

    settings = get_settings()
    start = time.monotonic()
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        messages = []
        if system_override:
            messages.append({"role": "system", "content": system_override})
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({"role": "user", "content": message})
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.3,
            max_tokens=1000,
        )
        text = response.choices[0].message.content or ""
    except Exception as e:
        logger.error("LLM call failed: %s", e)
        text = "I'm sorry, I'm having trouble processing your request."

    elapsed = int((time.monotonic() - start) * 1000)
    return {"response": text, "latency_ms": elapsed, "escalated": False}


def _get_client_ip(request: Request) -> str:
    return request.headers.get("x-forwarded-for", request.client.host or "unknown").split(",")[0].strip()


async def _fire_outgoing_webhooks(db: Session, tenant_id, user_id: str, event: str, result: dict):
    """Send outgoing webhooks directly (no Celery) for configured events."""
    import httpx

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

    if not cfg.outgoing_url:
        return

    body = json.dumps(payload, ensure_ascii=False)
    headers = {"Content-Type": "application/json"}
    if cfg.outgoing_secret:
        from .webhooks import compute_outgoing_signature
        from .crypto import decrypt
        try:
            secret = decrypt(cfg.outgoing_secret)
            headers["X-Jeeves-Signature"] = compute_outgoing_signature(secret, body)
        except Exception:
            pass

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.post(cfg.outgoing_url, content=body, headers=headers)
    except Exception as e:
        logger.warning("outgoing webhook failed: %s", e)




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
    db.commit()

    result = await _simple_llm_response(tenant.id, body.message)

    log.response = result["response"]
    log.resolution = "resolved"
    log.latency_ms = result["latency_ms"]
    log.session_id = session_id
    tenant.dialogs_used += 1
    tenant.resolved_count += 1
    db.commit()

    # Fire outgoing webhooks for configured events
    if result.get("action_called"):
        await _fire_outgoing_webhooks(db, tenant.id, body.user_id, "action.called", result)
    if result.get("escalated"):
        await _fire_outgoing_webhooks(db, tenant.id, body.user_id, "conversation.escalated", result)
    await _fire_outgoing_webhooks(db, tenant.id, body.user_id, "conversation.ended", result)

    return ChatOut(
        response=result["response"],
        action_called="",
        latency_ms=result["latency_ms"],
        escalated=False,
        resolution="resolved",
    )
