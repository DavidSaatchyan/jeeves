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
    ApprovalRequest,
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


# ─── Redirects from old pages to new simplified navigation ──────

_REDIRECT_MAP = {
    "/workflows": "",
    "/escalations": "",
    "/approvals": "",
    "/inbox": "/customers",
    "/analytics": "",
    "/timeline": "",
    "/logs": "",
    "/proactive": "",
    "/tools": "",
    "/billing": "/settings",
    "/integrations": "/settings",
    "/policies": "/settings",
    "/api": "/settings",
    "/crm": "/settings",
    "/widget-preview": "/settings",
}

for _old_path, _suffix in _REDIRECT_MAP.items():
    _target = f"/admin{_suffix}"

    def _mk_redir(path: str = _target):
        return RedirectResponse(url=path, status_code=status.HTTP_302_FOUND)

    router.get(_old_path, response_class=HTMLResponse)(_mk_redir)



@router.get("/customers", response_class=HTMLResponse)
def customers_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "customers.html", context=_ctx(request))


@router.get("/customers/{customer_id}", response_class=HTMLResponse)
def customer_detail_page(
    request: Request,
    customer_id: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    import uuid
    try:
        cid = uuid.UUID(customer_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid customer ID")
    cust = db.query(Customer).filter(Customer.id == cid, Customer.tenant_id == tenant.id).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    return templates.TemplateResponse(request, "customer_detail.html", context={**_ctx(request), "customer_id": customer_id})


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "settings.html", context=_ctx(request))


@router.get("/connections", response_class=HTMLResponse)
def connections_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "connections.html", context=_ctx(request))


@router.get("/automations", response_class=HTMLResponse)
def automations_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "automations.html", context=_ctx(request))


@router.get("/agents", response_class=HTMLResponse)
def agents_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "agents.html", context=_ctx(request))


@router.get("/knowledge", response_class=HTMLResponse)
def knowledge_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "knowledge.html", context=_ctx(request))


@router.get("/channels", response_class=HTMLResponse)
def channels_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "channels.html", context=_ctx(request))


@router.get("/account", response_class=HTMLResponse)
def account_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "account.html", context=_ctx(request))


@router.get("/workflows/{workflow_id}", response_class=HTMLResponse)
def workflow_detail_page(
    request: Request,
    workflow_id: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    import uuid
    try:
        wf_id = uuid.UUID(workflow_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid workflow ID")
    wf = db.query(Workflow).filter(Workflow.id == wf_id, Workflow.tenant_id == tenant.id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    transitions = (
        db.query(WorkflowTransition)
        .filter(WorkflowTransition.workflow_id == wf_id)
        .order_by(WorkflowTransition.created_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        request,
        "workflow_detail.html",
        context={**_ctx(request), "workflow": wf, "transitions": transitions},
    )


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


@router.post("/api/workflows/{workflow_id}/replay")
def api_workflow_replay(
    workflow_id: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    try:
        wf_id = uuid.UUID(workflow_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid workflow ID")
    wf = db.query(Workflow).filter(Workflow.id == wf_id, Workflow.tenant_id == tenant.id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    wf.status = "active"
    wf.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "message": "Workflow replayed"}


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


@router.get("/api/timeline")
def api_timeline(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    event_type: str | None = Query(None),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    q = db.query(TimelineEvent).filter(TimelineEvent.tenant_id == tenant.id)
    if event_type:
        q = q.filter(TimelineEvent.event_type == event_type)
    if from_date:
        try:
            fd = datetime.strptime(from_date, "%Y-%m-%d")
            q = q.filter(TimelineEvent.created_at >= fd)
        except ValueError:
            pass
    if to_date:
        try:
            td = datetime.strptime(to_date, "%Y-%m-%d") + timedelta(days=1)
            q = q.filter(TimelineEvent.created_at < td)
        except ValueError:
            pass
    total = q.count()
    rows = q.order_by(TimelineEvent.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "events": [
            {
                "id": str(e.id),
                "event_type": e.event_type,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "event_source": e.event_source,
                "payload": e.payload,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in rows
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/api/escalations")
def api_escalations(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    status: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    q = db.query(Escalation).filter(Escalation.tenant_id == tenant.id)
    if status:
        q = q.filter(Escalation.status == status)
    total = q.count()
    rows = q.order_by(Escalation.created_at.desc()).offset(offset).limit(limit).all()
    now = datetime.utcnow()
    return {
        "escalations": [
            {
                "id": str(e.id),
                "workflow_id": str(e.workflow_id) if e.workflow_id else None,
                "customer_id": str(e.customer_id) if e.customer_id else None,
                "reason": e.escalation_reason,
                "severity": e.severity,
                "status": e.status,
                "assigned_to": e.assigned_to,
                "source": e.source,
                "sla_breached": e.sla_breached or False,
                "sla_hours_left": None,
                "extra_metadata": e.extra_metadata,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "resolved_at": e.resolved_at.isoformat() if e.resolved_at else None,
                "updated_at": e.updated_at.isoformat() if e.updated_at else None,
            }
            for e in rows
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.post("/api/escalations/{esc_id}/assign")
def api_escalation_assign(
    esc_id: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    try:
        eid = uuid.UUID(esc_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid escalation ID")
    esc = db.query(Escalation).filter(Escalation.id == eid, Escalation.tenant_id == tenant.id).first()
    if not esc:
        raise HTTPException(status_code=404, detail="Escalation not found")
    esc.assigned_to = str(tenant.id)
    esc.status = "ASSIGNED"
    esc.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "message": "Escalation assigned"}


@router.post("/api/escalations/{esc_id}/resolve")
def api_escalation_resolve(
    esc_id: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    try:
        eid = uuid.UUID(esc_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid escalation ID")
    esc = db.query(Escalation).filter(Escalation.id == eid, Escalation.tenant_id == tenant.id).first()
    if not esc:
        raise HTTPException(status_code=404, detail="Escalation not found")
    esc.status = "RESOLVED"
    esc.resolved_at = datetime.utcnow()
    esc.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "message": "Escalation resolved"}


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

    approval_total = (
        db.query(func.count(ApprovalRequest.id))
        .filter(ApprovalRequest.tenant_id == tenant.id, ApprovalRequest.created_at >= thirty_days_ago)
        .scalar()
        or 0
    )
    approval_approved = (
        db.query(func.count(ApprovalRequest.id))
        .filter(ApprovalRequest.tenant_id == tenant.id, ApprovalRequest.status == "APPROVED", ApprovalRequest.created_at >= thirty_days_ago)
        .scalar()
        or 0
    )
    policy_overrides = (
        db.query(func.count(ApprovalRequest.id))
        .filter(ApprovalRequest.tenant_id == tenant.id, ApprovalRequest.status == "ALWAYS_ALLOW", ApprovalRequest.created_at >= thirty_days_ago)
        .scalar()
        or 0
    )

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

    # Approval Requests
    approvals = (
        db.query(
            ApprovalRequest.id,
            ApprovalRequest.workflow_id,
            ApprovalRequest.customer_id,
            ApprovalRequest.action_type,
            ApprovalRequest.risk_level,
            ApprovalRequest.ai_confidence,
            ApprovalRequest.status,
            ApprovalRequest.created_at,
        )
        .join(Workflow, Workflow.id == ApprovalRequest.workflow_id)
        .filter(
            Workflow.tenant_id == tenant.id,
            Workflow.workflow_type == agent_type,
            ApprovalRequest.created_at >= thirty_days_ago,
        )
        .order_by(ApprovalRequest.created_at.desc())
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
    for a in approvals:
        events.append({
            "id": str(a.id),
            "type": "approval",
            "workflow_id": str(a.workflow_id) if a.workflow_id else None,
            "customer_id": str(a.customer_id) if a.customer_id else None,
            "amount": None,
            "state": a.status,
            "action": a.action_type or "",
            "reason": "",
            "confidence": a.ai_confidence,
            "needs_human": True,
            "icon": "✅",
            "created_at": a.created_at.isoformat() if a.created_at else None,
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


@router.get("/api/agents/{agent_type}/roi")
def api_agent_roi(
    agent_type: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    """ROI metrics per plan section 1.3."""
    from sqlalchemy import text as sqla_text
    now = datetime.utcnow()
    thirty_days_ago = now - timedelta(days=30)
    seven_days_ago = now - timedelta(days=7)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    workflows = (
        db.query(Workflow)
        .filter(Workflow.tenant_id == tenant.id, Workflow.workflow_type == agent_type, Workflow.started_at >= thirty_days_ago)
        .all()
    )

    total = len(workflows)
    recovered = sum(1 for w in workflows if w.current_state in ("RECOVERED", "RETAINED", "RESOLVED"))
    failed = sum(1 for w in workflows if w.current_state in ("FAILED", "CANCELLED", "EXPIRED"))
    active = sum(1 for w in workflows if w.status in ("active", "paused"))
    escalated = sum(1 for w in workflows if w.status == "escalated")

    # Revenue recovered: sum of completed recoveries by time window
    def _recovered_revenue_since(since_dt):
        cnt = sum(1 for w in workflows
                  if w.current_state in ("RECOVERED", "RETAINED", "RESOLVED")
                  and w.completed_at and w.completed_at >= since_dt)
        return round(cnt * 29.99, 2)

    revenue_recovered = {
        "today": _recovered_revenue_since(today_start),
        "7d": _recovered_revenue_since(seven_days_ago),
        "30d": _recovered_revenue_since(thirty_days_ago),
    }

    # Revenue at risk — sum amount_due from active workflows
    at_risk_row = db.execute(
        sqla_text("""
            SELECT COALESCE(SUM(i.amount_due), 0) as total_at_risk
            FROM workflows w
            LEFT JOIN invoices i ON i.workflow_id = w.id
            WHERE w.tenant_id = :tid AND w.workflow_type = :wtype
              AND w.status IN ('active', 'paused')
        """),
        {"tid": tenant.id, "wtype": agent_type},
    ).scalar() or 0
    revenue_at_risk = float(at_risk_row)

    # Recovered customers (distinct)
    recovered_customers = len(set(
        w.customer_id for w in workflows
        if w.current_state in ("RECOVERED", "RETAINED", "RESOLVED") and w.customer_id
    ))
    active_at_risk = sum(1 for w in workflows if w.status in ("active", "paused"))
    awaiting_review = 0  # filled from approval queue in frontend

    # Support hours saved
    support_hours_saved = round(recovered * 0.5, 1)

    # Automation rate
    automation_rate = round(((total - escalated - failed) / total * 100) if total > 0 else 0, 1)
    recovery_rate = round((recovered / total * 100) if total > 0 else 0, 1)

    # Avg resolution time
    resolved = [w for w in workflows if w.current_state in ("RECOVERED", "RETAINED", "RESOLVED") and w.completed_at and w.started_at]
    if resolved:
        avg_hours = sum((w.completed_at - w.started_at).total_seconds() / 3600 for w in resolved) / len(resolved)
    else:
        avg_hours = None

    # Daily bar chart data
    daily = db.execute(
        sqla_text("""
            SELECT DATE(wt.created_at) as d, COUNT(*) as cnt
            FROM workflow_transitions wt
            JOIN workflows w ON w.id = wt.workflow_id
            WHERE w.tenant_id = :tid AND w.workflow_type = :wtype
              AND wt.to_state IN ('RECOVERED', 'RETAINED', 'RESOLVED')
              AND wt.created_at >= :since
            GROUP BY DATE(wt.created_at)
            ORDER BY d
        """),
        {"tid": tenant.id, "wtype": agent_type, "since": seven_days_ago},
    ).all()

    daily_revenue = []
    for d in daily:
        daily_revenue.append({"date": d.d.isoformat() if d.d else "", "count": d.cnt, "revenue": round(d.cnt * 29.99, 2)})

    return {
        "revenue_recovered": revenue_recovered,
        "revenue_at_risk": round(revenue_at_risk, 2),
        "support_hours_saved": support_hours_saved,
        "automation_rate": automation_rate,
        "recovery_rate": recovery_rate,
        "total_workflows": total,
        "active_workflows": active,
        "avg_resolution_time_hours": round(avg_hours, 1) if avg_hours else None,
        "recovered": recovered,
        "failed": failed,
        "escalated": escalated,
        "recovered_customers": recovered_customers,
        "active_at_risk": active_at_risk,
        "awaiting_review": awaiting_review,
        "daily_revenue": daily_revenue,
        "agent_type": agent_type,
    }


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

    elif queue == "approvals":
        q = db.query(ApprovalRequest).filter(
            ApprovalRequest.tenant_id == tenant.id,
            ApprovalRequest.status == "PENDING",
        )
        if agent_type != "all":
            q = q.join(Workflow, Workflow.id == ApprovalRequest.workflow_id).filter(
                Workflow.workflow_type == agent_type
            )
        total = q.count()
        rows = q.order_by(ApprovalRequest.created_at.desc()).offset(offset).limit(limit).all()
        return {
            "queue": queue,
            "items": [
                {
                    "id": str(a.id),
                    "workflow_id": str(a.workflow_id) if a.workflow_id else None,
                    "customer_id": str(a.customer_id) if a.customer_id else None,
                    "action_type": a.action_type,
                    "action_value": a.action_value,
                    "reason": a.reason,
                    "risk_level": a.risk_level,
                    "ai_confidence": a.ai_confidence,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in rows
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


@router.post("/api/agents/{agent_type}/queue/approve")
def api_agent_queue_approve(
    agent_type: str,
    body: _QueueActionBody,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    """Approve a pending approval request."""
    req = db.query(ApprovalRequest).filter(
        ApprovalRequest.id == body.item_id,
        ApprovalRequest.tenant_id == tenant.id,
        ApprovalRequest.status == "PENDING",
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Approval request not found")
    req.status = "APPROVED"
    req.reviewed_by = "admin"
    req.reviewed_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "message": "Approved"}


@router.post("/api/agents/{agent_type}/queue/reject")
def api_agent_queue_reject(
    agent_type: str,
    body: _QueueActionBody,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    """Reject a pending approval request."""
    req = db.query(ApprovalRequest).filter(
        ApprovalRequest.id == body.item_id,
        ApprovalRequest.tenant_id == tenant.id,
        ApprovalRequest.status == "PENDING",
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Approval request not found")
    req.status = "REJECTED"
    req.reviewed_by = "admin"
    req.reviewed_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "message": "Rejected"}


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


@router.get("/api/customers")
def api_customers(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    search: str | None = Query(None),
    risk: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    q = db.query(Customer).filter(Customer.tenant_id == tenant.id)
    if search:
        like = f"%{search}%"
        q = q.filter(Customer.email.ilike(like) | Customer.phone.ilike(like))
    if risk:
        q = q.filter(Customer.risk_level == risk)
    total = q.count()
    rows = q.order_by(Customer.last_seen_at.desc().nullslast()).offset(offset).limit(limit).all()
    return {
        "customers": [
            {
                "id": str(c.id),
                "email": c.email,
                "phone": c.phone,
                "risk_level": c.risk_level,
                "sentiment_state": c.sentiment_state,
                "frustration_score": c.frustration_score,
                "first_seen_at": c.first_seen_at.isoformat() if c.first_seen_at else None,
                "last_seen_at": c.last_seen_at.isoformat() if c.last_seen_at else None,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in rows
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/api/customers/{customer_id}")
def api_customer_detail(
    customer_id: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    try:
        cid = uuid.UUID(customer_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid customer ID")
    c = db.query(Customer).filter(Customer.id == cid, Customer.tenant_id == tenant.id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")
    return {
        "id": str(c.id),
        "email": c.email,
        "phone": c.phone,
        "shopify_customer_id": c.shopify_customer_id,
        "stripe_customer_id": c.stripe_customer_id,
        "recharge_customer_id": c.recharge_customer_id,
        "risk_level": c.risk_level,
        "sentiment_state": c.sentiment_state,
        "frustration_score": c.frustration_score,
        "first_seen_at": c.first_seen_at.isoformat() if c.first_seen_at else None,
        "last_seen_at": c.last_seen_at.isoformat() if c.last_seen_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.get("/api/customers/{customer_id}/timeline")
def api_customer_timeline(
    customer_id: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
):
    events = (
        db.query(TimelineEvent)
        .filter(TimelineEvent.tenant_id == tenant.id, TimelineEvent.entity_id == customer_id)
        .order_by(TimelineEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "events": [
            {
                "id": str(e.id),
                "event_type": e.event_type,
                "entity_type": e.entity_type,
                "event_source": e.event_source,
                "payload": e.payload,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ]
    }


@router.get("/api/customers/{customer_id}/context")
def api_customer_context(
    customer_id: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    """AI context panel data — risk, sentiment, recent activity, recommended actions."""
    try:
        cid = uuid.UUID(customer_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid customer ID")
    c = db.query(Customer).filter(Customer.id == cid, Customer.tenant_id == tenant.id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")

    active_workflows = (
        db.query(Workflow)
        .filter(Workflow.tenant_id == tenant.id, Workflow.customer_id == customer_id, Workflow.status.in_(["active", "paused"]))
        .count()
    )
    open_escalations = (
        db.query(Escalation)
        .filter(Escalation.tenant_id == tenant.id, Escalation.customer_id == cid, Escalation.status == "OPEN")
        .count()
    )
    recent_chats = (
        db.query(ChatLog)
        .filter(ChatLog.tenant_id == tenant.id, ChatLog.user_id == customer_id)
        .order_by(ChatLog.created_at.desc())
        .limit(5)
        .all()
    )

    return {
        "customer_id": str(c.id),
        "risk_level": c.risk_level,
        "sentiment_state": c.sentiment_state,
        "frustration_score": c.frustration_score,
        "active_workflows": active_workflows,
        "open_escalations": open_escalations,
        "recent_activity": [
            {
                "id": str(ch.id),
                "message": (ch.message or "")[:150],
                "channel": ch.channel,
                "resolution": ch.resolution,
                "created_at": ch.created_at.isoformat() if ch.created_at else None,
            }
            for ch in recent_chats
        ],
        "recommended_actions": [],
    }


# ─── Inbox API ─────────────────────────────────────────────────────────


@router.get("/api/inbox")
def api_inbox(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    channel: str | None = Query(None),
    resolution: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """Conversation list grouped by session_id."""
    subq = (
        db.query(
            ChatLog.session_id,
            func.max(ChatLog.created_at).label("last_at"),
            func.count(ChatLog.id).label("turns"),
        )
        .filter(ChatLog.tenant_id == tenant.id, ChatLog.session_id.isnot(None))
    )
    if channel:
        subq = subq.filter(ChatLog.channel == channel)
    subq = subq.group_by(ChatLog.session_id).subquery()

    q = (
        db.query(
            subq.c.session_id,
            subq.c.last_at,
            subq.c.turns,
            ChatLog.message,
            ChatLog.response,
            ChatLog.resolution,
            ChatLog.channel,
            ChatLog.user_id,
        )
        .select_from(subq)
        .outerjoin(ChatLog, ChatLog.session_id == subq.c.session_id)
    )
    if resolution:
        q = q.filter(ChatLog.resolution == resolution)
    q = q.order_by(subq.c.last_at.desc()).offset(offset).limit(limit)
    rows = q.all()

    total = db.query(subq).count()

    seen = set()
    result = []
    for r in rows:
        sid = r.session_id
        if sid in seen:
            continue
        seen.add(sid)
        customer_name = None
        if r.user_id:
            try:
                cust = db.query(Customer).filter(Customer.email == r.user_id, Customer.tenant_id == tenant.id).first()
                if cust and cust.name:
                    customer_name = cust.name
            except Exception:
                pass
        result.append({
            "session_id": str(sid),
            "user_id": r.user_id,
            "customer_name": customer_name,
            "channel": r.channel,
            "resolution": r.resolution,
            "turns": r.turns,
            "last_message": (r.message or "")[:200],
            "last_response": (r.response or "")[:200],
            "last_at": r.last_at.isoformat() if r.last_at else None,
        })

    return {"conversations": result, "total": total, "offset": offset, "limit": limit}


@router.get("/api/inbox/{session_id}")
def api_inbox_thread(
    session_id: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    """Full conversation thread for a session."""
    messages = (
        db.query(ChatLog)
        .filter(ChatLog.tenant_id == tenant.id, ChatLog.session_id == session_id)
        .order_by(ChatLog.created_at.asc())
        .all()
    )
    return {
        "session_id": session_id,
        "messages": [
            {
                "id": str(m.id),
                "direction": m.direction,
                "message": m.message,
                "response": m.response,
                "resolution": m.resolution,
                "channel": m.channel,
                "user_id": m.user_id,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }


@router.post("/api/inbox/{session_id}/takeover")
def api_inbox_takeover(
    session_id: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    """Mark a conversation as human takeover."""
    messages = (
        db.query(ChatLog)
        .filter(ChatLog.tenant_id == tenant.id, ChatLog.session_id == session_id)
        .all()
    )
    if not messages:
        raise HTTPException(status_code=404, detail="Conversation not found")
    for m in messages:
        m.resolution = "escalated"
    db.commit()
    return {"ok": True, "message": "Conversation taken over"}


@router.post("/api/inbox/{session_id}/suggest")
def api_inbox_suggest(
    session_id: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    """AI assist — generate reply suggestion (stub, returns placeholder)."""
    messages = (
        db.query(ChatLog)
        .filter(ChatLog.tenant_id == tenant.id, ChatLog.session_id == session_id)
        .order_by(ChatLog.created_at.desc())
        .limit(5)
        .all()
    )
    if not messages:
        raise HTTPException(status_code=404, detail="Conversation not found")

    context = "\n".join(
        f"{'Customer' if m.direction == 'incoming' else 'AI'}: {m.message or m.response or ''}"
        for m in reversed(messages)
    )

    return {
        "ok": True,
        "suggestion": "I understand your concern. Let me check on this for you right away.",
        "context": context[:500],
        "confidence": 85,
    }


# ─── Approval API ──────────────────────────────────────────────────────


@router.get("/api/approvals")
def api_approvals(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    status: str | None = Query(None),
    risk: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    q = db.query(ApprovalRequest).filter(ApprovalRequest.tenant_id == tenant.id)
    if status:
        q = q.filter(ApprovalRequest.status == status)
    if risk:
        q = q.filter(ApprovalRequest.risk_level == risk)
    total = q.count()
    rows = q.order_by(ApprovalRequest.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "approvals": [
            {
                "id": str(a.id),
                "workflow_id": str(a.workflow_id) if a.workflow_id else None,
                "customer_id": str(a.customer_id) if a.customer_id else None,
                "action_type": a.action_type,
                "action_value": a.action_value,
                "reason": a.reason,
                "expected_outcome": a.expected_outcome,
                "risk_level": a.risk_level,
                "ai_confidence": a.ai_confidence,
                "status": a.status,
                "reviewed_by": a.reviewed_by,
                "reviewed_at": a.reviewed_at.isoformat() if a.reviewed_at else None,
                "policy_reference": a.policy_reference,
                "simulation_result": a.simulation_result,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "updated_at": a.updated_at.isoformat() if a.updated_at else None,
            }
            for a in rows
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/api/approvals/{approval_id}")
def api_approval_detail(
    approval_id: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    try:
        aid = uuid.UUID(approval_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid approval ID")
    a = db.query(ApprovalRequest).filter(ApprovalRequest.id == aid, ApprovalRequest.tenant_id == tenant.id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Approval not found")
    return {
        "id": str(a.id),
        "workflow_id": str(a.workflow_id) if a.workflow_id else None,
        "customer_id": str(a.customer_id) if a.customer_id else None,
        "action_type": a.action_type,
        "action_value": a.action_value,
        "reason": a.reason,
        "expected_outcome": a.expected_outcome,
        "risk_level": a.risk_level,
        "ai_confidence": a.ai_confidence,
        "status": a.status,
        "reviewed_by": a.reviewed_by,
        "reviewed_at": a.reviewed_at.isoformat() if a.reviewed_at else None,
        "policy_reference": a.policy_reference,
        "simulation_result": a.simulation_result,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


@router.post("/api/approvals/{approval_id}/approve")
def api_approval_approve(
    approval_id: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    try:
        aid = uuid.UUID(approval_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid approval ID")
    a = db.query(ApprovalRequest).filter(ApprovalRequest.id == aid, ApprovalRequest.tenant_id == tenant.id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Approval not found")
    a.status = "APPROVED"
    a.reviewed_by = str(tenant.id)
    a.reviewed_at = datetime.utcnow()
    a.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "message": "Approved", "status": a.status}


@router.post("/api/approvals/{approval_id}/always")
def api_approval_always(
    approval_id: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    try:
        aid = uuid.UUID(approval_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid approval ID")
    a = db.query(ApprovalRequest).filter(ApprovalRequest.id == aid, ApprovalRequest.tenant_id == tenant.id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Approval not found")
    a.status = "ALWAYS_ALLOW"
    a.reviewed_by = str(tenant.id)
    a.reviewed_at = datetime.utcnow()
    a.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "message": "Always allowed under policy", "status": a.status}


@router.post("/api/approvals/{approval_id}/reject")
def api_approval_reject(
    approval_id: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    try:
        aid = uuid.UUID(approval_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid approval ID")
    a = db.query(ApprovalRequest).filter(ApprovalRequest.id == aid, ApprovalRequest.tenant_id == tenant.id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Approval not found")
    a.status = "REJECTED"
    a.reviewed_by = str(tenant.id)
    a.reviewed_at = datetime.utcnow()
    a.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "message": "Rejected", "status": a.status}


@router.post("/api/approvals/{approval_id}/escalate")
def api_approval_escalate(
    approval_id: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    try:
        aid = uuid.UUID(approval_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid approval ID")
    a = db.query(ApprovalRequest).filter(ApprovalRequest.id == aid, ApprovalRequest.tenant_id == tenant.id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Approval not found")
    a.status = "ESCALATED"
    a.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "message": "Escalated", "status": a.status}


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
