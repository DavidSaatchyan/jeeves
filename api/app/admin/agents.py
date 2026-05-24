from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    AIInteraction,
    Communication,
    Escalation,
    Invoice,
    PolicySet,
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

    escalations = (
        db.query(
            Escalation.id,
            Escalation.workflow_id,
            Escalation.customer_id,
            Escalation.escalation_reason,
            Escalation.severity,
            Escalation.status,
            Escalation.created_at,
        )
        .join(Workflow, Workflow.id == Escalation.workflow_id)
        .filter(
            Workflow.tenant_id == tenant.id,
            Workflow.workflow_type == agent_type,
            Escalation.created_at >= thirty_days_ago,
        )
        .order_by(Escalation.created_at.desc())
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
    for e in escalations:
        events.append({
            "id": str(e.id),
            "type": "escalation",
            "workflow_id": str(e.workflow_id) if e.workflow_id else None,
            "customer_id": str(e.customer_id) if e.customer_id else None,
            "amount": None,
            "state": e.status,
            "action": e.severity + ": " + (e.escalation_reason or ""),
            "reason": e.escalation_reason or "",
            "confidence": None,
            "needs_human": True,
            "icon": "⚠️",
            "created_at": e.created_at.isoformat() if e.created_at else None,
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

    WISMO_FUNNEL = {
        "Detected": {"states": ["INQUIRY_DETECTED", "VALIDATING_IDENTITY"], "order": 0, "color": "#6366f1"},
        "Identified": {"states": ["RETRIEVING_SHIPMENT", "CLASSIFYING_RISK"], "order": 1, "color": "#818cf8"},
        "Informed": {"states": ["RESPONSE_SENT"], "order": 2, "color": "#f59e0b"},
        "Resolved": {"states": ["RESOLVED"], "order": 3, "color": "#10b981"},
        "Lost": {"states": ["LOST"], "order": 4, "color": "#ef4444"},
    }
    PAYGUARD_FUNNEL = {
        "Detected": {"states": ["DETECTED", "VALIDATING"], "order": 0, "color": "#6366f1"},
        "Classified": {"states": ["CLASSIFYING_FAILURE", "SELECTING_STRATEGY"], "order": 1, "color": "#818cf8"},
        "Outreach": {"states": ["OUTREACH_PENDING", "OUTREACH_SENT", "WAITING_CUSTOMER"], "order": 2, "color": "#f59e0b"},
        "Retry": {"states": ["RETRY_SCHEDULED", "RETRY_PENDING", "RETRYING", "VERIFYING_RESULT", "PAUSED_RECONCILIATION"], "order": 3, "color": "#22d3ee"},
        "Recovered": {"states": ["RECOVERED"], "order": 4, "color": "#10b981"},
    }
    FUNNEL_STAGES = WISMO_FUNNEL if agent_type == "wismo" else PAYGUARD_FUNNEL
    DROP_STATES = {"FAILED", "ESCALATED", "EXPIRED"}

    LABELS = {
        "Detected": "Order inquiries detected",
        "Identified": "Orders identified and fetched",
        "Informed": "Notifications sent",
        "Resolved": "Successfully resolved",
        "Lost": "Lost packages",
        "Classified": "Classified as recoverable",
        "Outreach": "Outreach sent",
        "Retry": "Retry executed",
        "Recovered": "Successfully recovered",
    }

    row_map = {r.current_state: r.cnt for r in rows}
    total = sum(row_map.values())

    stages = []
    prev_count = total
    for label, cfg in sorted(FUNNEL_STAGES.items(), key=lambda x: x[1]["order"]):
        count = sum(row_map.get(s, 0) for s in cfg["states"])
        pct = round((count / total * 100) if total > 0 else 0)
        drop_off = prev_count - count if label != "Detected" else 0
        drop_reason = ""
        if drop_off > 0:
            reasons = []
            for s in DROP_STATES:
                if s in row_map:
                    reasons.append(s.lower())
            drop_reason = f"{'blocked' if 'esc' in str(reasons) else 'skipped'}" if reasons else ""
        stages.append({
            "state": label,
            "count": count,
            "label": LABELS.get(label, label),
            "pct": pct,
            "color": cfg["color"],
            "drop_off": drop_off,
            "drop_reason": drop_reason,
        })
        prev_count = count

    drop_offs = []
    for i in range(1, len(stages)):
        if stages[i-1]["drop_off"] > 0:
            drop_offs.append({
                "from": stages[i-1]["state"],
                "to": stages[i]["state"],
                "drop": stages[i-1]["drop_off"],
                "reason": stages[i-1]["drop_reason"],
            })

    return {"stages": stages, "drop_offs": drop_offs, "agent_type": agent_type}


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
            func.coalesce(
                db.query(func.sum(Invoice.amount_due))
                .filter(Invoice.workflow_id == Workflow.id)
                .scalar_subquery(), 0
            ).label("amount_due"),
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
                    "amount_due": float(r.amount_due) if r.amount_due else None,
                    "risk_level": "medium",
                    "started_at": r.started_at.isoformat() if r.started_at else None,
                }
                for r in rows
            ],
            "total": total,
        }

    elif queue == "escalations":
        q = db.query(Escalation).filter(
            Escalation.tenant_id == tenant.id,
            Escalation.status == "OPEN",
        )
        if agent_type != "all":
            q = q.join(Workflow, Workflow.id == Escalation.workflow_id).filter(
                Workflow.workflow_type == agent_type
            )
        total = q.count()
        rows = q.order_by(Escalation.created_at.desc()).offset(offset).limit(limit).all()
        return {
            "queue": queue,
            "items": [
                {
                    "id": str(e.id),
                    "workflow_id": str(e.workflow_id) if e.workflow_id else None,
                    "customer_id": str(e.customer_id) if e.customer_id else None,
                    "reason": e.escalation_reason,
                    "severity": e.severity,
                    "assigned_to": e.assigned_to,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in rows
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
    ps = db.query(PolicySet).filter(PolicySet.tenant_id == tenant.id).first()
    if not ps:
        ps = PolicySet(tenant_id=tenant.id)
        db.add(ps)

    field_map = {
        "recovery_strategy": "retry_policy",
        "communication": "communication_policy",
        "approval_rules": "approval_policy",
        "escalation_rules": "escalation_policy",
    }
    field = field_map.get(body.section)
    if field:
        existing = getattr(ps, field) or {}
        existing.update(body.values)
        setattr(ps, field, existing)
        ps.updated_at = datetime.utcnow()
        db.commit()
        return {"ok": True, "message": f"Policy section '{body.section}' updated"}

    return {"ok": False, "message": f"Unknown policy section: {body.section}"}


@router.post("/api/agents/{agent_type}/queue/resolve")
def api_agent_queue_resolve(
    agent_type: str,
    body: _QueueActionBody,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    esc = db.query(Escalation).filter(
        Escalation.id == body.item_id,
        Escalation.tenant_id == tenant.id,
        Escalation.status == "OPEN",
    ).first()
    if not esc:
        raise HTTPException(status_code=404, detail="Escalation not found")
    esc.status = "RESOLVED"
    esc.resolved_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "message": "Resolved"}
