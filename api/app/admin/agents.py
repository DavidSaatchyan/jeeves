from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    AIInteraction,
    Communication,
    Tenant,
    TimelineEvent,
    Workflow,
    WorkflowTransition,
)
from .deps import get_admin_tenant
from .router import router


class _QueueActionBody(BaseModel):
    item_id: str


class _PolicyUpdateBody(BaseModel):
    section: str
    values: dict = {}


@router.get("/api/agents/{agent_type}/feed")
def api_agent_feed(
    agent_type: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    since: str | None = Query(None),
):
    limit = 50
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    since_dt = thirty_days_ago
    if since:
        try:
            parsed = datetime.fromisoformat(since)
            if parsed > since_dt:
                since_dt = parsed
        except ValueError:
            pass

    transitions = (
        db.query(
            WorkflowTransition.id,
            WorkflowTransition.workflow_id,
            Workflow.customer_id,
            WorkflowTransition.from_state,
            WorkflowTransition.to_state,
            WorkflowTransition.decision_reason,
            WorkflowTransition.created_at,
        )
        .join(Workflow, Workflow.id == WorkflowTransition.workflow_id)
        .filter(
            Workflow.tenant_id == tenant.id,
            Workflow.workflow_type == agent_type,
            WorkflowTransition.created_at >= since_dt,
        )
        .order_by(WorkflowTransition.created_at.desc())
        .limit(limit)
        .all()
    )

    comms = (
        db.query(
            Communication.id,
            Communication.workflow_id,
            Communication.customer_id,
            Communication.channel,
            Communication.template_name,
            Communication.delivery_status,
            Communication.sent_at,
        )
        .join(Workflow, Workflow.id == Communication.workflow_id)
        .filter(
            Workflow.tenant_id == tenant.id,
            Workflow.workflow_type == agent_type,
            Communication.created_at >= since_dt,
        )
        .order_by(Communication.created_at.desc())
        .limit(limit)
        .all()
    )

    ai_ints = (
        db.query(AIInteraction)
        .join(Workflow, Workflow.id == AIInteraction.workflow_id)
        .filter(
            Workflow.tenant_id == tenant.id,
            Workflow.workflow_type == agent_type,
            AIInteraction.created_at >= since_dt,
        )
        .order_by(AIInteraction.created_at.desc())
        .limit(limit)
        .all()
    )

    events = []
    for t in transitions:
        is_success = t.to_state in ("RECOVERED", "RETAINED", "RESOLVED")
        is_active = t.to_state in ("RETRYING", "OUTREACH_SENT", "WAITING_CUSTOMER")
        is_escalated = t.to_state == "ESCALATED"
        icon = "💰" if is_success else "⚠️" if is_escalated else "🔄"
        events.append({
            "id": str(t.id),
            "type": "transition",
            "workflow_id": str(t.workflow_id),
            "customer_id": str(t.customer_id) if t.customer_id else None,
            "amount": None,
            "state": t.to_state,
            "action": t.to_state or t.from_state or "",
            "reason": t.decision_reason or "",
            "confidence": None,
            "needs_human": False,
            "icon": icon,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        })
    for c in comms:
        events.append({
            "id": str(c.id),
            "type": "communication",
            "workflow_id": str(c.workflow_id),
            "customer_id": str(c.customer_id) if c.customer_id else None,
            "amount": None,
            "state": c.delivery_status,
            "action": c.channel + ": " + (c.template_name or ""),
            "reason": "",
            "confidence": None,
            "needs_human": False,
            "icon": "📧",
            "created_at": c.sent_at.isoformat() if c.sent_at else None,
        })
    for ai in ai_ints:
        events.append({
            "id": str(ai.id),
            "type": "ai_decision",
            "workflow_id": str(ai.workflow_id) if ai.workflow_id else None,
            "customer_id": None,
            "amount": None,
            "state": ai.interaction_type or "classified",
            "action": ai.interaction_type or "classification",
            "reason": ai.output or "",
            "confidence": ai.confidence,
            "needs_human": ai.confidence is not None and ai.confidence < 70,
            "icon": "🧠",
            "created_at": ai.created_at.isoformat() if ai.created_at else None,
        })

    events.sort(key=lambda e: e.get("created_at") or "", reverse=True)
    return {"events": events[:limit]}


@router.get("/api/agents/{agent_type}/funnel")
def api_agent_funnel(
    agent_type: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text("""
            SELECT current_state, COUNT(*) as cnt
            FROM workflows
            WHERE tenant_id = :tid AND workflow_type = :wtype
            GROUP BY current_state
            ORDER BY cnt DESC
        """),
        {"tid": str(tenant.id), "wtype": agent_type},
    ).all()

    row_map = {r.current_state: r.cnt for r in rows}
    total = sum(row_map.values())

    stages = [
        {
            "state": s,
            "count": c,
            "label": s,
            "pct": round((c / total * 100) if total > 0 else 0),
            "color": "#6366f1",
            "drop_off": 0,
            "drop_reason": "",
        }
        for s, c in sorted(row_map.items(), key=lambda x: x[1], reverse=True)
    ]

    return {"stages": stages, "drop_offs": [], "agent_type": agent_type}


@router.get("/api/agents/{agent_type}/queue")
def api_agent_queue(
    agent_type: str,
    queue: str = "active",
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    if queue == "active":
        q = db.query(
            Workflow.id,
            Workflow.customer_id,
            Workflow.current_state,
            Workflow.status,
            Workflow.started_at,
        ).filter(
            Workflow.tenant_id == tenant.id,
            Workflow.workflow_type == agent_type,
            Workflow.status.in_(["active", "paused"]),
        )
        total = q.count()
        rows = q.order_by(Workflow.started_at.desc()).offset(offset).limit(limit).all()
        return {
            "queue": queue,
            "items": [
                {
                    "id": str(r.id),
                    "customer_id": r.customer_id,
                    "current_state": r.current_state,
                    "status": r.status,
                    "started_at": r.started_at.isoformat() if r.started_at else None,
                }
                for r in rows
            ],
            "total": total,
        }

    elif queue == "log":
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        q = db.query(TimelineEvent).filter(
            TimelineEvent.tenant_id == tenant.id,
            TimelineEvent.entity_type == "workflow",
            TimelineEvent.created_at >= thirty_days_ago,
        )
        if agent_type != "all":
            q = q.filter(TimelineEvent.event_type.like(f"{agent_type}%"))
        total = q.count()
        rows = q.order_by(TimelineEvent.created_at.desc()).offset(offset).limit(limit).all()
        return {
            "queue": queue,
            "items": [
                {
                    "id": str(r.id),
                    "event_type": r.event_type,
                    "entity_id": r.entity_id,
                    "payload": r.payload,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ],
            "total": total,
        }

    return {"queue": queue, "items": [], "total": 0}


@router.put("/api/agents/{agent_type}/policy")
def api_agent_policy_update(
    agent_type: str,
    body: _PolicyUpdateBody,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    return {"ok": True, "message": f"Policy section '{body.section}' updated (placeholder)"}


@router.post("/api/agents/{agent_type}/queue/resolve")
def api_agent_queue_resolve(
    agent_type: str,
    body: _QueueActionBody,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    return {"ok": True, "message": "Resolved (placeholder)"}
