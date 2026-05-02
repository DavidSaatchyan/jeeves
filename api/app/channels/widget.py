"""Web-widget channel: serves `widget.js` loader and accepts unauthenticated
chat requests scoped by data-tenant-id. Outgoing (proactive) messages are
pulled from an inbox endpoint.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import ChatLog, Tenant, WebhookConfig, WriteBackConfig
from ..schemas import ChatOut, WidgetChatIn
from .. import agent, billing

router = APIRouter(tags=["widget"])

# Serve the widget loader script (frontend/widget.js).
# In docker, ./frontend is mounted at /app/frontend. Fall back to relative lookup otherwise.
_WIDGET_JS_PATH = Path("/app/frontend/widget.js")
if not _WIDGET_JS_PATH.exists():
    _WIDGET_JS_PATH = Path(__file__).resolve().parents[3] / "frontend" / "widget.js"

_FRONTEND_DIR = Path("/app/frontend")
if not _FRONTEND_DIR.exists():
    _FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"


def _enqueue_outgoing_webhooks(db: Session, tenant_id, user_id: str, event: str, result: dict):
    try:
        from tasks import send_outgoing_webhook
    except ImportError:
        return

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
        print(f"[widget] webhook enqueue failed: {e}", flush=True)


def _enqueue_writeback(db: Session, tenant_id, session_id: str):
    try:
        from tasks import writeback_conversation
    except ImportError:
        return

    cfg = db.query(WriteBackConfig).filter(
        WriteBackConfig.tenant_id == tenant_id,
    ).first()
    if not cfg or cfg.type == "off":
        return

    try:
        writeback_conversation.delay(str(tenant_id), session_id)
    except Exception as e:
        print(f"[widget] writeback enqueue failed: {e}", flush=True)


@router.get("/widget.js")
def widget_js():
    if not _WIDGET_JS_PATH.exists():
        raise HTTPException(404, "widget.js not built")
    return Response(
        content=_WIDGET_JS_PATH.read_text(encoding="utf-8"),
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=60"},
    )


@router.get("/dashboard")
def dashboard():
    path = _FRONTEND_DIR / "index.html"
    if not path.exists():
        raise HTTPException(404, "dashboard not built")
    return Response(
        content=path.read_text(encoding="utf-8"),
        media_type="text/html",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/dashboard.css")
def dashboard_css():
    path = _FRONTEND_DIR / "dashboard.css"
    if not path.exists():
        raise HTTPException(404, "dashboard.css not found")
    return Response(
        content=path.read_text(encoding="utf-8"),
        media_type="text/css",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/dashboard.js")
def dashboard_js():
    path = _FRONTEND_DIR / "dashboard.js"
    if not path.exists():
        raise HTTPException(404, "dashboard.js not found")
    return Response(
        content=path.read_text(encoding="utf-8"),
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.post("/widget/chat", response_model=ChatOut)
async def widget_chat(body: WidgetChatIn):
    """Unauthenticated widget entry point — tenant is identified by tenant_id from data-attr."""
    db: Session = SessionLocal()
    try:
        tenant = db.get(Tenant, body.tenant_id)
        if not tenant:
            raise HTTPException(404, "tenant not found")
        billing.enforce(tenant)

        session_id = uuid.uuid4()

        # Log incoming
        log = ChatLog(
            tenant_id=tenant.id,
            user_id=body.user_id,
            direction="incoming",
            message=body.message,
            extra_fields=body.extra_fields or {},
            session_id=session_id,
        )
        db.add(log)
        db.commit()

        result = await agent.run(
            db, tenant.id, body.user_id, body.message,
            extra_fields=body.extra_fields or {},
            session_id=session_id,
        )

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
        )
    finally:
        db.close()


@router.get("/widget/inbox")
def widget_inbox(tenant_id: uuid.UUID, user_id: str):
    """Return any undelivered outgoing (proactive) messages for this user."""
    db: Session = SessionLocal()
    try:
        rows = (
            db.query(ChatLog)
            .filter(
                ChatLog.tenant_id == tenant_id,
                ChatLog.user_id == user_id,
                ChatLog.direction == "outgoing",
                ChatLog.delivered == False,  # noqa: E712
            )
            .order_by(ChatLog.created_at.asc())
            .all()
        )
        out = [{"id": str(r.id), "message": r.response, "created_at": r.created_at.isoformat()} for r in rows]
        for r in rows:
            r.delivered = True
        db.commit()
        return {"messages": out}
    finally:
        db.close()
