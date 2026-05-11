"""Admin Dashboard (FR-6) — server-rendered Jinja2 pages.

DEFAULT: minimal SSR to avoid shipping a separate SPA. Pages call the same
JSON API endpoints via fetch() from inline scripts.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from datetime import datetime, timedelta

from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, text, Integer, and_
from sqlalchemy.orm import Session

from .auth import decode_token, get_current_tenant, issue_tokens
from . import billing
from .config import get_settings
from .db import get_db
from .models import (
    AIInteraction,
    ApiKey,
    ChatLog,
    Communication,
    ConversationRating,
    Customer,
    Escalation,
    NativeConnector,
    NotificationPreferences,
    PolicySet,
    TimelineEvent,
    Workflow,
    WorkflowTransition,
    Tenant,
)

router = APIRouter(prefix="/admin", tags=["admin"])

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_SESSION_COOKIE = "jeeves_session"


def get_admin_tenant(
    request: Request,
    token: Optional[str] = Cookie(default=None, alias=_SESSION_COOKIE),
    db: Session = Depends(get_db),
) -> Tenant:
    """Extract tenant from session cookie OR Authorization Bearer header."""
    raw = token
    if not raw:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            raw = auth[7:]
    if not raw:
        raise HTTPException(status_code=status.HTTP_302_FOUND, headers={"Location": "/admin/login"})
    try:
        payload = decode_token(raw)
    except HTTPException:
        raise HTTPException(status_code=status.HTTP_302_FOUND, headers={"Location": "/admin/login"})
    if payload.get("kind") != "access":
        raise HTTPException(status_code=status.HTTP_302_FOUND, headers={"Location": "/admin/login"})
    import uuid
    tenant = db.get(Tenant, uuid.UUID(payload["sub"]))
    if not tenant:
        raise HTTPException(status_code=status.HTTP_302_FOUND, headers={"Location": "/admin/login"})
    return tenant


def _ctx(request: Request) -> dict:
    s = get_settings()
    base = s.public_base_url
    if not base or base == "http://localhost:8000":
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get("x-forwarded-host", request.url.netloc)
        base = f"{scheme}://{host}"
    return {"public_base_url": base}


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def home(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return RedirectResponse(url="/admin/agents", status_code=status.HTTP_302_FOUND)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", context=_ctx(request))


@router.post("/login", response_class=HTMLResponse)
async def admin_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    from .models import Tenant
    from passlib.context import CryptContext
    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

    tenant = db.query(Tenant).filter(Tenant.email == email).first()
    pw = password.encode("utf-8")[:72].decode("utf-8", errors="ignore")
    if not tenant or not pwd_ctx.verify(pw, tenant.hashed_password):
        return RedirectResponse(
            url="/admin/login?error=invalid",
            status_code=status.HTTP_302_FOUND,
        )

    access, _ = issue_tokens(tenant.id)
    response = RedirectResponse(url="/admin", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=_SESSION_COOKIE,
        value=access,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=900,  # 15 minutes
        path="/admin",
    )
    return response


@router.post("/logout", response_class=HTMLResponse)
def admin_logout():
    response = RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key=_SESSION_COOKIE, path="/admin")
    return response


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "settings.html", context=_ctx(request))


@router.get("/connections", response_class=HTMLResponse)
def connections_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "connections.html", context=_ctx(request))


@router.get("/agents", response_class=HTMLResponse)
def agents_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "agents.html", context=_ctx(request))


@router.get("/knowledge", response_class=HTMLResponse)
def knowledge_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    ctx = _ctx(request)
    ctx["tenant_id"] = str(tenant.id)
    return templates.TemplateResponse(request, "knowledge.html", context=ctx)


@router.get("/channels", response_class=HTMLResponse)
def channels_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "channels.html", context=_ctx(request))


@router.get("/account", response_class=HTMLResponse)
def account_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "account.html", context=_ctx(request))


# ─── /admin/api/ JSON endpoints ────────────────────────────────────────

import uuid


def _admin_api_dep(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    return tenant, db


@router.get("/api/integrations")
def api_integrations(
    request: Request,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    ctx = _ctx(request)
    base = ctx.get("public_base_url", "").rstrip("/")
    webhook_base = f"{base}/integrations/webhooks" if base else None

    PROVIDER_WEBHOOK_EVENTS = {
        "shopify": ["orders/create", "orders/updated", "fulfillments/create", "fulfillments/update", "customers/create", "customers/update"],
        "recharge": ["subscription/cancelled", "charge/failed", "charge/success", "subscription/skipped"],
        "stripe": ["invoice.payment_failed", "invoice.payment_succeeded", "customer.subscription.updated", "customer.subscription.deleted"],
    }

    PROVIDER_REQUIRED_FIELDS = {
        "shopify": ["shop_domain", "access_token"],
        "recharge": ["api_key"],
        "stripe": ["secret_key"],
    }

    from .crypto import decrypt

    connectors = db.query(NativeConnector).filter(NativeConnector.tenant_id == tenant.id).all()
    conn_map = {c.provider: c for c in connectors}

    result = []
    for provider in ("shopify", "recharge", "stripe"):
        c = conn_map.get(provider)
        status = "disconnected"
        if c and c.status == "connected":
            try:
                creds = json.loads(decrypt(c.credentials))
                required = PROVIDER_REQUIRED_FIELDS.get(provider, [])
                if all(creds.get(f) for f in required):
                    status = "connected"
                else:
                    status = "disconnected"
            except Exception:
                status = "disconnected"

        result.append({
            "provider": provider,
            "status": status,
            "has_webhook_secret": bool((c.meta or {}).get("webhook_secret")) if c else False,
            "webhook_url": f"{webhook_base}/{provider}" if webhook_base else None,
            "webhook_events": PROVIDER_WEBHOOK_EVENTS.get(provider, []),
            "created_at": c.created_at.isoformat() if c and c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c and c.updated_at else None,
        })

    return {
        "native_connectors": result,
        "webhook_base_url": webhook_base,
    }


@router.get("/api/workflows")
def api_workflows(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    workflow_type: str | None = Query(None, alias="type"),
    status: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    q = db.query(Workflow).filter(Workflow.tenant_id == tenant.id)
    if workflow_type:
        q = q.filter(Workflow.workflow_type == workflow_type)
    if status:
        q = q.filter(Workflow.status == status)
    total = q.count()
    rows = q.order_by(Workflow.started_at.desc()).offset(offset).limit(limit).all()
    return {
        "workflows": [
            {
                "id": str(w.id),
                "workflow_type": w.workflow_type,
                "customer_id": w.customer_id,
                "current_state": w.current_state,
                "status": w.status,
                "started_at": w.started_at.isoformat() if w.started_at else None,
                "updated_at": w.updated_at.isoformat() if w.updated_at else None,
                "completed_at": w.completed_at.isoformat() if w.completed_at else None,
                "priority": w.priority,
            }
            for w in rows
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/api/workflows/{workflow_id}/timeline")
def api_workflow_timeline(
    workflow_id: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    import uuid
    try:
        wf_id = uuid.UUID(workflow_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid workflow ID")
    events = (
        db.query(TimelineEvent)
        .filter(
            TimelineEvent.tenant_id == tenant.id,
            TimelineEvent.entity_type == "workflow",
            TimelineEvent.entity_id == workflow_id,
        )
        .order_by(TimelineEvent.created_at.desc())
        .limit(100)
        .all()
    )
    return {
        "events": [
            {
                "id": str(e.id),
                "event_type": e.event_type,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "payload": e.payload,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ]
    }



@router.post("/api/workflows/{workflow_id}/escalate")
def api_workflow_escalate(
    workflow_id: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    from .models import Customer
    try:
        wf_id = uuid.UUID(workflow_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid workflow ID")
    wf = db.query(Workflow).filter(Workflow.id == wf_id, Workflow.tenant_id == tenant.id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    wf.status = "escalated"
    wf.updated_at = datetime.utcnow()

    customer_uuid = None
    if wf.customer_id:
        try:
            cid = uuid.UUID(wf.customer_id)
            if db.query(Customer.id).filter(Customer.id == cid).first():
                customer_uuid = cid
        except (ValueError, TypeError):
            pass

    if customer_uuid:
        esc = Escalation(
            tenant_id=tenant.id,
            workflow_id=wf_id,
            customer_id=customer_uuid,
            escalation_reason="Manual escalation from admin",
            severity="high",
            status="OPEN",
        )
        db.add(esc)

    db.commit()
    return {"ok": True, "message": "Workflow escalated"}






@router.get("/api/policies")
def api_policies(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    ps = db.query(PolicySet).filter(PolicySet.tenant_id == tenant.id).first()
    if not ps:
        return {
            "retry": None,
            "communication": None,
            "escalation": None,
            "approval": None,
            "enabled_workflows": [],
        }
    return {
        "retry": ps.retry_policy,
        "communication": ps.communication_policy,
        "escalation": ps.escalation_policy,
        "approval": ps.approval_policy,
        "enabled_workflows": ps.enabled_workflows or [],
    }


@router.put("/api/policies/{policy_type}")
def api_policies_update(
    policy_type: str,
    body: dict,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    ps = db.query(PolicySet).filter(PolicySet.tenant_id == tenant.id).first()
    if not ps:
        ps = PolicySet(tenant_id=tenant.id)
        db.add(ps)
    field_map = {
        "retry": "retry_policy",
        "communication": "communication_policy",
        "escalation": "escalation_policy",
        "approval": "approval_policy",
        "enabled_workflows": "enabled_workflows",
    }
    field = field_map.get(policy_type)
    if not field:
        raise HTTPException(status_code=400, detail=f"Unknown policy type: {policy_type}")
    setattr(ps, field, body)
    ps.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "message": f"Policy '{policy_type}' updated"}


@router.get("/api/analytics")
def api_analytics(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    workflows = (
        db.query(Workflow)
        .filter(Workflow.tenant_id == tenant.id, Workflow.started_at >= thirty_days_ago)
        .all()
    )

    total = len(workflows)
    recovered = sum(1 for w in workflows if w.current_state in ("RECOVERED", "RETAINED", "RESOLVED"))
    failed = sum(1 for w in workflows if w.current_state in ("FAILED", "CANCELLED"))
    active = sum(1 for w in workflows if w.status in ("active", "paused"))

    recovered_revenue = recovered * 29.99  # Estimated avg MRR per recovery

    esc_count = (
        db.query(func.count(Escalation.id))
        .filter(Escalation.tenant_id == tenant.id, Escalation.created_at >= thirty_days_ago)
        .scalar()
        or 0
    )

    comms_count = (
        db.query(func.count(Communication.id))
        .filter(Communication.tenant_id == tenant.id, Communication.created_at >= thirty_days_ago)
        .scalar()
        or 0
    )

    approval_total = 0
    approval_approved = 0
    policy_overrides = 0

    return {
        "recovered_revenue": round(recovered_revenue, 2),
        "save_rate": round((recovered / total * 100) if total > 0 else 0, 1),
        "churn_prevented": recovered,
        "avg_resolution_time": "-",
        "total_workflows": total,
        "active_workflows": active,
        "recovered": recovered,
        "failed": failed,
        "escalations": esc_count,
        "communications_sent": comms_count,
        "avg_response_time": "-",
        "total_approvals": approval_total,
        "approved_approvals": approval_approved,
        "escalation_accuracy": "-",
        "policy_overrides": policy_overrides,
    }


# ─── Agent API (per plan-payguard-redesign.md) ──────────────────────────


@router.get("/api/agents/{agent_type}/feed")
def api_agent_feed(
    agent_type: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    since: str | None = Query(None),
):
    """Unified live feed: transitions, approvals, escalations, communications, AI decisions."""
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

    # Transitions → merged with workflow data for customer_id
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

    # Communications
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

    # Escalations
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

    # AI interactions
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
        action = t.to_state or t.from_state or ""
        is_success = t.to_state in ("RECOVERED", "RETAINED", "RESOLVED")
        is_active = t.to_state in ("RETRYING", "OUTREACH_SENT", "WAITING_CUSTOMER")
        is_escalated = t.to_state == "ESCALATED"
        icon = "💰" if is_success else "⚠️" if is_escalated else "🔄" if is_active else "🔄"
        events.append({
            "id": str(t.id),
            "type": "transition",
            "workflow_id": str(t.workflow_id),
            "customer_id": str(t.customer_id) if t.customer_id else None,
            "amount": None,
            "state": t.to_state,
            "action": action,
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
    """Funnel breakdown with drop-off analysis per plan D2."""
    from sqlalchemy import text

    rows = db.execute(
        text("""
            SELECT current_state, COUNT(*) as cnt
            FROM workflows
            WHERE tenant_id = :tid AND workflow_type = :wtype
            GROUP BY current_state
            ORDER BY cnt DESC
        """),
        {"tid": tenant.id, "wtype": agent_type},
    ).all()

    # Funnel stage mapping (plan D2)
    FUNNEL_STAGES = {
        "Detected": {"states": ["DETECTED", "VALIDATING"], "order": 0, "color": "#6366f1"},
        "Classified": {"states": ["CLASSIFYING_FAILURE", "SELECTING_STRATEGY"], "order": 1, "color": "#818cf8"},
        "Outreach": {"states": ["OUTREACH_PENDING", "OUTREACH_SENT", "WAITING_CUSTOMER"], "order": 2, "color": "#f59e0b"},
        "Retry": {"states": ["RETRY_SCHEDULED", "RETRY_PENDING", "RETRYING", "VERIFYING_RESULT", "PAUSED_RECONCILIATION"], "order": 3, "color": "#22d3ee"},
        "Recovered": {"states": ["RECOVERED"], "order": 4, "color": "#10b981"},
    }
    DROP_STATES = {"FAILED", "ESCALATED", "EXPIRED"}

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
            "label": f"Failed payments detected" if label == "Detected" else
                     f"Classified as recoverable" if label == "Classified" else
                     f"Outreach sent" if label == "Outreach" else
                     f"Retry executed" if label == "Retry" else
                     f"Successfully recovered",
            "pct": pct,
            "color": cfg["color"],
            "drop_off": drop_off,
            "drop_reason": drop_reason,
        })
        prev_count = count

    # Drop-off between stages (plan format)
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
    """Queue tabs: active, approvals, escalations, log."""
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
                    "id": str(e.id),
                    "event_type": e.event_type,
                    "entity_id": e.entity_id,
                    "payload": e.payload,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in rows
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
    """Save simplified agent policy. Merges into existing policy set."""
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
    section = body.section
    field = field_map.get(section)
    if field:
        existing = getattr(ps, field) or {}
        existing.update(body.values)
        setattr(ps, field, existing)
        ps.updated_at = datetime.utcnow()
        db.commit()
        return {"ok": True, "message": f"Policy section '{section}' updated"}

    return {"ok": False, "message": f"Unknown policy section: {section}"}


class _QueueActionBody(BaseModel):
    item_id: str


class _PolicyUpdateBody(BaseModel):
    section: str
    values: dict = {}


@router.post("/api/agents/{agent_type}/queue/resolve")
def api_agent_queue_resolve(
    agent_type: str,
    body: _QueueActionBody,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    """Resolve an open escalation."""
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


# ─── Billing / Logs / Ratings API (moved from dashboard_api) ──────────


@router.get("/api/billing")
def api_billing(tenant: Tenant = Depends(get_admin_tenant)):
    return billing.usage(tenant)


@router.get("/api/logs")
def api_logs(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    user_id: str | None = None,
    session_id: str | None = None,
    channel: str | None = None,
    resolution: str | None = None,
    days: int = 30,
    limit: int = 50,
    last_id: str | None = None,
):
    limit = min(limit, 200)
    q = db.query(ChatLog).filter(ChatLog.tenant_id == tenant.id)
    if user_id:
        q = q.filter(ChatLog.user_id == user_id)
    if session_id:
        q = q.filter(ChatLog.session_id == session_id)
    if channel:
        q = q.filter(ChatLog.channel == channel)
    if resolution:
        q = q.filter(ChatLog.resolution == resolution)
    q = q.filter(ChatLog.created_at >= datetime.utcnow() - timedelta(days=days))
    if last_id:
        last_log = db.query(ChatLog.created_at).filter(ChatLog.id == last_id).first()
        if last_log:
            q = q.filter(ChatLog.created_at < last_log.created_at)
    rows = q.order_by(ChatLog.created_at.desc()).limit(limit + 1).all()
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:-1]

    session_ids = set(r.session_id for r in rows if r.session_id)
    sessions = {}
    if session_ids:
        session_rows = (
            db.query(
                ChatLog.session_id,
                func.count(ChatLog.id).label("turns"),
                func.min(ChatLog.created_at).label("started_at"),
                func.max(ChatLog.created_at).label("last_at"),
            )
            .filter(ChatLog.session_id.in_(session_ids))
            .group_by(ChatLog.session_id)
            .all()
        )
        for sr in session_rows:
            sessions[str(sr.session_id)] = {
                "turns": sr.turns,
                "started_at": sr.started_at.isoformat() if sr.started_at else None,
                "last_at": sr.last_at.isoformat() if sr.last_at else None,
            }

    next_cursor = str(rows[-1].id) if rows and has_more else None
    return {
        "logs": [
            {
                "id": str(r.id),
                "session_id": str(r.session_id) if r.session_id else None,
                "created_at": r.created_at.isoformat(),
                "user_id": r.user_id,
                "direction": r.direction,
                "message": r.message,
                "response": r.response,
                "resolution": r.resolution,
                "action_called": r.action_called,
                "latency_ms": r.latency_ms,
                "delivered": r.delivered,
                "sources": r.sources or [],
                "channel": r.channel,
                "extra_fields": r.extra_fields or {},
                "session_info": sessions.get(str(r.session_id)) if r.session_id else None,
            }
            for r in rows
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@router.post("/api/ratings", status_code=201)
def api_submit_rating(
    body: dict,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    rating = ConversationRating(
        tenant_id=tenant.id,
        user_id=body.get("user_id", ""),
        message_id=body.get("message_id"),
        rating=body.get("rating", "thumbs_up"),
        feedback=body.get("feedback", ""),
    )
    db.add(rating)
    db.commit()
    return {"ok": True, "id": str(rating.id)}


@router.get("/api/ratings")
def api_list_ratings(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    user_id: str | None = None,
    days: int = 30,
    limit: int = 50,
    last_id: str | None = None,
):
    limit = min(limit, 200)
    q = db.query(ConversationRating).filter(ConversationRating.tenant_id == tenant.id)
    if user_id:
        q = q.filter(ConversationRating.user_id == user_id)
    q = q.filter(ConversationRating.created_at >= datetime.utcnow() - timedelta(days=days))
    if last_id:
        last_rating = db.query(ConversationRating.created_at).filter(ConversationRating.id == last_id).first()
        if last_rating:
            q = q.filter(ConversationRating.created_at < last_rating.created_at)
    rows = q.order_by(ConversationRating.created_at.desc()).limit(limit + 1).all()
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:-1]

    next_cursor = str(rows[-1].id) if rows and has_more else None
    return {
        "ratings": [
            {
                "id": str(r.id),
                "user_id": r.user_id,
                "message_id": str(r.message_id) if r.message_id else None,
                "rating": r.rating,
                "feedback": r.feedback,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


# ─── Customer API ──────────────────────────────────────────────────────






# ─── Inbox API ─────────────────────────────────────────────────────────






# ─── Approval API ──────────────────────────────────────────────────────








# ─── Settings API ──────────────────────────────────────────────────────


@router.get("/api/settings")
def api_settings(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    prefs = db.query(NotificationPreferences).filter(NotificationPreferences.tenant_id == tenant.id).first()
    keys = db.query(ApiKey).filter(ApiKey.tenant_id == tenant.id).order_by(ApiKey.created_at.desc()).all()
    return {
        "workspace": {
            "name": tenant.name,
            "email": tenant.email,
            "plan": "free",
            "trial_ends": tenant.trial_ends.isoformat() if tenant.trial_ends else None,
            "is_active": tenant.is_active,
        },
        "api_keys": [
            {
                "id": str(k.id),
                "name": k.name,
                "prefix": k.prefix,
                "created_at": k.created_at.isoformat() if k.created_at else None,
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                "expires_at": k.expires_at.isoformat() if k.expires_at else None,
            }
            for k in keys
        ],
        "notifications": {
            "escalation_alerts": prefs.escalation_alerts if prefs else True,
            "approval_alerts": prefs.approval_alerts if prefs else True,
            "workflow_failure_alerts": prefs.workflow_failure_alerts if prefs else True,
            "daily_summary": prefs.daily_summary if prefs else False,
        } if prefs else {
            "escalation_alerts": True,
            "approval_alerts": True,
            "workflow_failure_alerts": True,
            "daily_summary": False,
        },
        "billing": billing.usage(tenant),
    }


@router.put("/api/settings")
def api_settings_update(
    body: dict,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    prefs = db.query(NotificationPreferences).filter(NotificationPreferences.tenant_id == tenant.id).first()
    if not prefs:
        prefs = NotificationPreferences(tenant_id=tenant.id)
        db.add(prefs)
    notifications = body.get("notifications", {})
    if "escalation_alerts" in notifications:
        prefs.escalation_alerts = bool(notifications["escalation_alerts"])
    if "approval_alerts" in notifications:
        prefs.approval_alerts = bool(notifications["approval_alerts"])
    if "workflow_failure_alerts" in notifications:
        prefs.workflow_failure_alerts = bool(notifications["workflow_failure_alerts"])
    if "daily_summary" in notifications:
        prefs.daily_summary = bool(notifications["daily_summary"])
    prefs.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "message": "Settings updated"}


@router.post("/api/settings/api-keys")
def api_settings_create_key(
    body: dict,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    import hashlib, secrets
    name = body.get("name", "default")
    raw = "jev_sk_" + secrets.token_hex(24)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    prefix = raw[:12]
    key = ApiKey(tenant_id=tenant.id, name=name, key_hash=hashed, prefix=prefix)
    db.add(key)
    db.commit()
    return {"ok": True, "raw_key": raw, "prefix": prefix, "name": name}


@router.delete("/api/settings/api-keys/{key_id}")
def api_settings_delete_key(
    key_id: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    try:
        kid = uuid.UUID(key_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid key ID")
    key = db.query(ApiKey).filter(ApiKey.id == kid, ApiKey.tenant_id == tenant.id).first()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    db.delete(key)
    db.commit()
    return {"ok": True, "message": "API key revoked"}
