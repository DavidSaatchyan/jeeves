"""Web-widget channel: serves `widget.js` loader and accepts unauthenticated
chat requests scoped by data-tenant-id. Outgoing (proactive) messages are
pulled from an inbox endpoint.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ChannelConfig, ChatLog, ConversationRating, Tenant
from ..moderation import moderate
from ..rate_limit import check_rate_limit
from ..schemas import ChatOut, WidgetChatIn
from ..routes_chat import _simple_llm_response

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
    db.commit()

    result = await _simple_llm_response(tenant.id, body.message)

    log.response = result["response"]
    log.resolution = "resolved"
    log.latency_ms = result["latency_ms"]
    log.session_id = session_id
    log.channel = body.channel or "web_widget"
    if log.channel != "test_widget":
        tenant.dialogs_used += 1
        tenant.resolved_count += 1
    db.commit()

    return ChatOut(
        response=result["response"],
        action_called="",
        latency_ms=result["latency_ms"],
        escalated=False,
        resolution="resolved",
    )


@router.get("/widget/inbox")
def widget_inbox(tenant_id: uuid.UUID, user_id: str, request: Request, db: Session = Depends(get_db)):
    """Return any undelivered outgoing (proactive) messages for this user."""
    _validate_origin_strict(tenant_id, request, db)
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
