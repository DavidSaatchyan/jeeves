"""Inbox / Operations Center — conversation management, handoff, customer profile."""
from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, func, or_, text
from sqlalchemy.orm import Session

from ..core.timeline.recorder import record_transition
from ..db import get_db
from ..shared.inbox_writer import add_message
from ..models import (
    CannedResponse,
    Communication,
    Conversation,
    Customer,
    Message,
    OperatorNote,
    Tenant,
    Workflow,
    WorkflowTransition,
)
from .deps import _ctx, get_admin_tenant
from .router import router, templates


# ── Pydantic Schemas ──


class CustomerBrief(BaseModel):
    id: UUID
    display_name: str | None = None
    email: str | None = None
    avatar_url: str | None = None


class WorkflowBrief(BaseModel):
    id: UUID | None = None
    type: str | None = None
    state: str | None = None
    status: str | None = None


class ConversationListItem(BaseModel):
    id: UUID
    customer: CustomerBrief | None = None
    channel: str
    status: str
    assigned_to: str | None = None
    workflow: WorkflowBrief | None = None
    last_message_preview: str | None = None
    message_count: int
    unread_count: int
    last_message_at: datetime
    started_at: datetime


class ConversationListResponse(BaseModel):
    conversations: list[ConversationListItem]
    total: int
    limit: int
    offset: int


class MessageOut(BaseModel):
    model_config = {"from_attributes": True}
    id: UUID
    direction: str
    content: str
    content_type: str
    sender_type: str
    operator_id: str | None = None
    workflow_state: str | None = None
    sources: dict | None = None
    confidence: float | None = None
    created_at: datetime


class NoteOut(BaseModel):
    model_config = {"from_attributes": True}
    id: UUID
    content: str
    operator_id: str
    created_at: datetime


# ── Helpers ──


def _add_system_event(db: Session, conv: Conversation, tenant: Tenant, text: str) -> Message:
    msg = Message(
        tenant_id=tenant.id,
        conversation_id=conv.id,
        direction="outgoing",
        content=text,
        content_type="system_event",
        sender_type="system",
    )
    db.add(msg)
    return msg


def _conversation_to_item(c: Conversation, db: Session) -> ConversationListItem:
    customer = None
    if c.customer_id:
        cust = db.get(Customer, c.customer_id)
        if cust:
            customer = CustomerBrief(
                id=cust.id,
                display_name=cust.email,
                email=cust.email,
            )
    wf = None
    if c.workflow_id:
        w = db.get(Workflow, c.workflow_id)
        if w:
            wf = WorkflowBrief(id=w.id, type=w.workflow_type, state=w.current_state, status=w.status)
    return ConversationListItem(
        id=c.id,
        customer=customer,
        channel=c.channel,
        status=c.status,
        assigned_to=c.assigned_to,
        workflow=wf,
        last_message_preview=c.last_message_preview,
        message_count=c.message_count,
        unread_count=c.unread_count,
        last_message_at=c.last_message_at,
        started_at=c.started_at,
    )


# ── Template Pages ──


@router.get("/inbox", include_in_schema=False)
def inbox_page(
    request: Request,
    tenant: Tenant = Depends(get_admin_tenant),
):
    ctx = _ctx(request)
    return templates.TemplateResponse(
        "inbox.html",
        {"request": request, **ctx},
    )


# ── API Endpoints ──


@router.get("/api/inbox/conversations")
def list_conversations(
    request: Request,
    status: str | None = Query(None),
    channel: str | None = Query(None),
    assignee: str | None = Query(None),
    q: str | None = Query(None),
    sort: str = Query("last_message_at"),
    order: str = Query("desc"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    query = select(Conversation).where(Conversation.tenant_id == tenant.id)

    if status:
        statuses = [s.strip() for s in status.split(",")]
        query = query.where(Conversation.status.in_(statuses))
    if channel:
        query = query.where(Conversation.channel == channel)
    if assignee == "unassigned":
        query = query.where(Conversation.assigned_to.is_(None))
    elif assignee == "me":
        query = query.where(Conversation.assigned_to == tenant.email)
    elif assignee:
        query = query.where(Conversation.assigned_to == assignee)
    if q:
        search = f"%{q}%"
        query = query.where(
            or_(
                Conversation.last_message_preview.ilike(search),
                Conversation.user_display_name.ilike(search),
                Conversation.user_id.ilike(search),
            )
        )

    count_query = select(func.count()).select_from(query.subquery())
    total = db.scalar(count_query) or 0

    sort_col = Conversation.last_message_at if sort == "last_message_at" else Conversation.created_at
    if order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    query = query.offset(offset).limit(limit)
    rows = db.execute(query).scalars().all()

    # Batch-load customers and workflows to avoid N+1
    customer_ids = {c.customer_id for c in rows if c.customer_id}
    workflow_ids = {c.workflow_id for c in rows if c.workflow_id}
    customers = {}
    if customer_ids:
        for c in db.execute(select(Customer).where(Customer.id.in_(customer_ids))).scalars():
            customers[c.id] = c
    workflows = {}
    if workflow_ids:
        for w in db.execute(select(Workflow).where(Workflow.id.in_(workflow_ids))).scalars():
            workflows[w.id] = w

    def _item(c: Conversation) -> ConversationListItem:
        customer = None
        if c.customer_id and c.customer_id in customers:
            cust = customers[c.customer_id]
            customer = CustomerBrief(id=cust.id, display_name=cust.email, email=cust.email)
        wf = None
        if c.workflow_id and c.workflow_id in workflows:
            w = workflows[c.workflow_id]
            wf = WorkflowBrief(id=w.id, type=w.workflow_type, state=w.current_state, status=w.status)
        return ConversationListItem(
            id=c.id, customer=customer, channel=c.channel, status=c.status,
            assigned_to=c.assigned_to, workflow=wf,
            last_message_preview=c.last_message_preview, message_count=c.message_count,
            unread_count=c.unread_count, last_message_at=c.last_message_at, started_at=c.started_at,
        )

    return ConversationListResponse(
        conversations=[_item(c) for c in rows],
        total=total,
        limit=limit,
        offset=offset,
    ).model_dump()


@router.get("/api/inbox/conversations/{conversation_id}")
def get_conversation(
    conversation_id: UUID,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    conv = db.scalar(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.tenant_id == tenant.id)
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return _conversation_to_item(conv, db).model_dump()


@router.get("/api/inbox/conversations/{conversation_id}/messages")
def get_messages(
    conversation_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    before: datetime | None = Query(None),
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    conv = db.scalar(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.tenant_id == tenant.id)
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    query = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    if before:
        query = query.where(Message.created_at < before)
    rows = db.execute(query).scalars().all()
    rows.reverse()
    return [MessageOut.model_validate(m).model_dump() for m in rows]


@router.post("/api/inbox/conversations/{conversation_id}/assign")
def assign_conversation(
    conversation_id: UUID,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    conv = db.scalar(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.tenant_id == tenant.id)
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conv.assigned_to = tenant.email
    conv.assigned_at = datetime.utcnow()
    if conv.status in ("active", "waiting", "handoff_requested"):
        conv.status = "assigned"
    _add_system_event(db, conv, tenant, f"Assigned to {tenant.email}")
    db.commit()
    return {"ok": True, "assigned_to": tenant.email}


@router.post("/api/inbox/conversations/{conversation_id}/close")
def close_conversation(
    conversation_id: UUID,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    conv = db.scalar(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.tenant_id == tenant.id)
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.status == "closed":
        raise HTTPException(status_code=400, detail="Conversation already closed")
    conv.status = "closed"
    conv.closed_at = datetime.utcnow()
    if conv.workflow_id:
        db.execute(
            text("UPDATE workflows SET status = 'completed' WHERE id = :id AND status IN ('active','paused')"),
            {"id": conv.workflow_id},
        )
    _add_system_event(db, conv, tenant, "Conversation closed")
    db.commit()
    return {"ok": True}


@router.post("/api/inbox/conversations/{conversation_id}/read")
def mark_conversation_read(
    conversation_id: UUID,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    conv = db.scalar(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.tenant_id == tenant.id)
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conv.unread_count = 0
    db.commit()
    return {"ok": True}


@router.post("/api/inbox/conversations/{conversation_id}/notes")
def add_note(
    conversation_id: UUID,
    body: dict,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    content = body.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Note content is required")
    conv = db.scalar(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.tenant_id == tenant.id)
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    note = OperatorNote(
        tenant_id=tenant.id,
        conversation_id=conversation_id,
        content=content,
        operator_id=tenant.email,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return NoteOut.model_validate(note).model_dump()


@router.get("/api/inbox/conversations/{conversation_id}/notes")
def get_notes(
    conversation_id: UUID,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    conv = db.scalar(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.tenant_id == tenant.id)
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    rows = db.execute(
        select(OperatorNote)
        .where(OperatorNote.conversation_id == conversation_id)
        .order_by(OperatorNote.created_at.asc())
    ).scalars().all()
    return [NoteOut.model_validate(n).model_dump() for n in rows]


@router.post("/api/inbox/messages/send")
def send_message(
    body: dict,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    conversation_id = body.get("conversation_id")
    content = body.get("content", "").strip()
    if not conversation_id or not content:
        raise HTTPException(status_code=400, detail="conversation_id and content are required")
    if len(content) > 5000:
        raise HTTPException(status_code=400, detail="Message too long (max 5000 chars)")
    conv = db.scalar(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.tenant_id == tenant.id)
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Dedup: prevent double-send from double-click within 2s window
    recent = db.scalar(
        select(Message).where(
            Message.conversation_id == conv.id,
            Message.direction == "outgoing",
            Message.sender_type == "operator",
            Message.content == content,
            Message.created_at >= datetime.utcnow() - timedelta(seconds=2),
        ).order_by(Message.created_at.desc())
    )
    if recent:
        db.refresh(recent)
        return MessageOut.model_validate(recent).model_dump()

    msg = add_message(
        db=db,
        conversation=conv,
        direction="outgoing",
        content=content,
        sender_type="operator",
        operator_id=tenant.email,
    )
    db.commit()
    db.refresh(msg)
    return MessageOut.model_validate(msg).model_dump()


@router.post("/api/inbox/conversations/{conversation_id}/takeover")
def takeover_conversation(
    conversation_id: UUID,
    body: dict,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    conv = db.scalar(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.tenant_id == tenant.id)
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.status == "closed":
        raise HTTPException(status_code=400, detail="Cannot take over a closed conversation")
    if conv.assigned_to and conv.assigned_to != tenant.email:
        previous_assignee = conv.assigned_to
    else:
        previous_assignee = None
    previous_status = conv.status
    conv.status = "assigned"
    conv.assigned_to = tenant.email
    conv.assigned_at = datetime.utcnow()

    take_msg = f"Operator {tenant.email} took over."
    if previous_assignee:
        take_msg += f" Previously assigned to {previous_assignee}."
    _add_system_event(db, conv, tenant, take_msg)

    if conv.workflow_id:
        db.execute(
            text("UPDATE workflows SET status = 'paused' WHERE id = :id AND status = 'active'"),
            {"id": conv.workflow_id},
        )
        record_transition(
            db=db,
            workflow_id=conv.workflow_id,
            workflow_type=conv.workflow_type or "unknown",
            from_state=conv.workflow_state or "",
            to_state=conv.workflow_state or "",
            trigger_event="operator_takeover",
            decision_reason=f"Operator {tenant.email} took over: {body.get('reason', 'manual takeover')}",
        )

    db.commit()
    return {
        "ok": True,
        "conversation_id": str(conversation_id),
        "previous_status": previous_status,
        "new_status": "assigned",
        "assigned_to": tenant.email,
    }


@router.post("/api/inbox/conversations/{conversation_id}/return-to-ai")
def return_to_ai(
    conversation_id: UUID,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    conv = db.scalar(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.tenant_id == tenant.id)
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.status == "closed":
        raise HTTPException(status_code=400, detail="Cannot return a closed conversation to AI")
    conv.status = "active"
    conv.assigned_to = None
    conv.assigned_at = None

    _add_system_event(db, conv, tenant, "Conversation returned to AI agent.")

    if conv.workflow_id:
        db.execute(
            text("UPDATE workflows SET status = 'active' WHERE id = :id AND status = 'paused'"),
            {"id": conv.workflow_id},
        )

    db.commit()
    return {"ok": True, "status": "active"}


# ── Customer Profile API ──


class CustomerProfileOut(BaseModel):
    model_config = {"from_attributes": True}
    id: UUID
    email: str | None = None
    phone: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    locale: str | None = None
    timezone: str | None = None
    tags: list | None = None
    total_conversations: int = 0
    total_workflows: int = 0
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    last_message_at: datetime | None = None
    risk_level: str | None = None
    sentiment_state: str | None = None
    sentiment_trend: str | None = None
    frustration_score: int | None = None
    created_at: datetime | None = None


@router.get("/api/customers/search")
def search_customers(
    q: str = Query("", min_length=1),
    limit: int = Query(20, ge=1, le=100),
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    query = select(Customer).where(Customer.tenant_id == tenant.id)
    if q:
        search = f"%{q}%"
        query = query.where(
            or_(
                Customer.email.ilike(search),
                Customer.display_name.ilike(search),
                Customer.phone.ilike(search),
            )
        )
    query = query.order_by(Customer.last_message_at.desc().nullslast()).limit(limit)
    rows = db.execute(query).scalars().all()
    return [CustomerProfileOut.model_validate(c).model_dump() for c in rows]


@router.get("/api/customers/{customer_id}")
def get_customer_profile(
    customer_id: UUID,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    cust = db.scalar(
        select(Customer).where(Customer.id == customer_id, Customer.tenant_id == tenant.id)
    )
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    return CustomerProfileOut.model_validate(cust).model_dump()


@router.get("/api/customers/{customer_id}/conversations")
def get_customer_conversations(
    customer_id: UUID,
    limit: int = Query(10, ge=1, le=50),
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    cust = db.scalar(
        select(Customer).where(Customer.id == customer_id, Customer.tenant_id == tenant.id)
    )
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    rows = (
        db.execute(
            select(Conversation)
            .where(
                Conversation.customer_id == customer_id,
                Conversation.tenant_id == tenant.id,
            )
            .order_by(Conversation.last_message_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [_conversation_to_item(c, db).model_dump() for c in rows]


@router.get("/api/customers/{customer_id}/workflows")
def get_customer_workflows(
    customer_id: UUID,
    limit: int = Query(10, ge=1, le=50),
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    cust = db.scalar(
        select(Customer).where(Customer.id == customer_id, Customer.tenant_id == tenant.id)
    )
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    rows = (
        db.execute(
            select(Workflow)
            .where(
                Workflow.customer_id == cust.email,
                Workflow.tenant_id == tenant.id,
            )
            .order_by(Workflow.started_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": str(w.id),
            "type": w.workflow_type,
            "state": w.current_state,
            "status": w.status,
            "started_at": w.started_at.isoformat() if w.started_at else None,
            "completed_at": w.completed_at.isoformat() if w.completed_at else None,
        }
        for w in rows
    ]


# ── Unified Timeline API ──


@router.get("/api/conversations/{conversation_id}/history")
def get_conversation_history(
    conversation_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    conv = db.scalar(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.tenant_id == tenant.id)
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    events: list[dict] = []

    # Messages
    msgs = db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    ).scalars().all()
    for m in msgs:
        events.append({
            "type": "message",
            "direction": m.direction,
            "content": m.content,
            "content_type": m.content_type,
            "sender_type": m.sender_type,
            "operator_id": m.operator_id,
            "created_at": m.created_at.isoformat(),
        })

    # Workflow transitions
    if conv.workflow_id:
        trans = db.execute(
            select(WorkflowTransition)
            .where(WorkflowTransition.workflow_id == conv.workflow_id)
            .order_by(WorkflowTransition.created_at.asc())
        ).scalars().all()
        for t in trans:
            events.append({
                "type": "workflow_transition",
                "from_state": t.from_state,
                "to_state": t.to_state,
                "reason": t.decision_reason,
                "created_at": t.created_at.isoformat(),
            })

    # Communications
    if conv.customer_id:
        comms = db.execute(
            select(Communication)
            .where(
                Communication.customer_id == conv.customer_id,
                Communication.tenant_id == tenant.id,
            )
            .order_by(Communication.created_at.asc())
        ).scalars().all()
        for c in comms:
            events.append({
                "type": "communication",
                "channel": c.channel,
                "template": c.template_name,
                "status": c.delivery_status,
                "created_at": c.created_at.isoformat(),
            })

    # Sort all events by created_at
    events.sort(key=lambda e: e["created_at"])

    return {"events": events[-limit:]}


# ── Auto-close inactive conversations ──

AUTO_CLOSE_HOURS = 24


def _auto_close_stale_conversations(db: Session, tenant_id: UUID) -> int:
    cutoff = datetime.utcnow() - timedelta(hours=AUTO_CLOSE_HOURS)
    stale = db.execute(
        select(Conversation)
        .where(
            Conversation.tenant_id == tenant_id,
            Conversation.status.in_(["active", "waiting"]),
            Conversation.last_message_at < cutoff,
        )
    ).scalars().all()
    for c in stale:
        c.status = "closed"
        c.closed_at = datetime.utcnow()
    db.commit()
    return len(stale)


# ── Canned Responses API ──


class CannedResponseOut(BaseModel):
    model_config = {"from_attributes": True}
    id: UUID
    title: str
    content: str
    shortcut: str | None = None
    category: str | None = None


class CannedResponseIn(BaseModel):
    title: str
    content: str
    shortcut: str | None = None
    category: str | None = None


@router.get("/api/inbox/canned-responses")
def list_canned_responses(
    category: str | None = Query(None),
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    query = select(CannedResponse).where(CannedResponse.tenant_id == tenant.id)
    if category:
        query = query.where(CannedResponse.category == category)
    query = query.order_by(CannedResponse.category, CannedResponse.title)
    rows = db.execute(query).scalars().all()
    return [CannedResponseOut.model_validate(r).model_dump() for r in rows]


@router.post("/api/inbox/canned-responses", status_code=201)
def create_canned_response(
    body: CannedResponseIn,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    cr = CannedResponse(
        tenant_id=tenant.id,
        title=body.title,
        content=body.content,
        shortcut=body.shortcut,
        category=body.category,
    )
    db.add(cr)
    db.commit()
    db.refresh(cr)
    return CannedResponseOut.model_validate(cr).model_dump()


@router.delete("/api/inbox/canned-responses/{response_id}")
def delete_canned_response(
    response_id: UUID,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    cr = db.scalar(
        select(CannedResponse).where(CannedResponse.id == response_id, CannedResponse.tenant_id == tenant.id)
    )
    if not cr:
        raise HTTPException(status_code=404, detail="Canned response not found")
    db.delete(cr)
    db.commit()
    return {"ok": True}


# ── Notification endpoint — client polls for handoff count ──


@router.get("/api/inbox/notifications")
def inbox_notifications(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    handoff_count = db.scalar(
        select(func.count())
        .select_from(Conversation)
        .where(
            Conversation.tenant_id == tenant.id,
            Conversation.status == "handoff_requested",
        )
    ) or 0

    total_unread = db.scalar(
        select(func.coalesce(func.sum(Conversation.unread_count), 0))
        .where(
            Conversation.tenant_id == tenant.id,
            Conversation.status != "closed",
        )
    ) or 0

    return {
        "handoff_requested": handoff_count,
        "total_unread": total_unread,
    }


# ── SSE streaming endpoint ──


@router.get("/api/inbox/events")
async def inbox_events(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    import asyncio
    import json

    from ..db import SessionLocal

    last_check = datetime.utcnow()

    async def _poll() -> list[dict] | None:
        nonlocal last_check
        def _sync_poll():
            s = SessionLocal()
            try:
                _auto_close_stale_conversations(s, tenant.id)
                q = s.execute(
                    select(Conversation)
                    .where(
                        Conversation.tenant_id == tenant.id,
                        Conversation.status.in_(["active", "waiting", "handoff_requested", "assigned"]),
                        Conversation.last_message_at > last_check,
                    )
                    .order_by(Conversation.last_message_at.desc())
                    .limit(20)
                )
                updated = q.scalars().all()
                if not updated:
                    return None
                convs = []
                for c in updated:
                    cust = s.get(Customer, c.customer_id) if c.customer_id else None
                    convs.append({
                        "id": str(c.id),
                        "status": c.status,
                        "assigned_to": c.assigned_to,
                        "last_message_preview": c.last_message_preview,
                        "unread_count": c.unread_count,
                        "customer_name": cust.display_name if cust else c.user_id,
                        "last_message_at": c.last_message_at.isoformat(),
                    })
                return convs
            finally:
                s.close()

        result = await asyncio.to_thread(_sync_poll)
        if result:
            last_check = datetime.utcnow()
            return result
        return None

    async def event_stream():
        while True:
            try:
                convs = await _poll()
                if convs:
                    yield f"data: {json.dumps({'type': 'conversations_updated', 'conversations': convs})}\n\n"
                else:
                    yield ": heartbeat\n\n"
            except Exception:
                pass
            await asyncio.sleep(3)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
