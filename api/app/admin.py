"""Admin Dashboard (FR-6) — server-rendered Jinja2 pages.

DEFAULT: minimal SSR to avoid shipping a separate SPA. Pages call the same
JSON API endpoints via fetch() from inline scripts.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from datetime import datetime, timedelta

from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, text, Integer, and_
from sqlalchemy.orm import Session

from .auth import decode_token, get_current_tenant, issue_tokens
from .config import get_settings
from .db import get_db
from .models import (
    AIInteraction,
    ApprovalRequest,
    ChatLog,
    Communication,
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
    token: Optional[str] = Cookie(default=None, alias=_SESSION_COOKIE),
    db: Session = Depends(get_db),
) -> Tenant:
    """Extract tenant from session cookie for admin pages."""
    if not token:
        raise HTTPException(status_code=status.HTTP_302_FOUND, headers={"Location": "/admin/login"})
    try:
        payload = decode_token(token)
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
    return templates.TemplateResponse(request, "overview.html", context=_ctx(request))


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
        secure=True,
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


@router.get("/knowledge", response_class=HTMLResponse)
def knowledge(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "knowledge.html", context=_ctx(request))


@router.get("/integrations", response_class=HTMLResponse)
def integrations_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "integrations.html", context=_ctx(request))


@router.get("/logs", response_class=HTMLResponse)
def logs_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "logs.html", context=_ctx(request))


@router.get("/channels", response_class=HTMLResponse)
def channels_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "channels.html", context=_ctx(request))


@router.get("/widget-preview", response_class=HTMLResponse)
def widget_preview(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "widget_preview.html", context=_ctx(request))


@router.get("/proactive", response_class=HTMLResponse)
def proactive_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "proactive.html", context=_ctx(request))


@router.get("/billing", response_class=HTMLResponse)
def billing_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "billing.html", context=_ctx(request))


@router.get("/tools", response_class=HTMLResponse)
def tools_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "tools.html", context=_ctx(request))


@router.get("/api", response_class=HTMLResponse)
def api_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "api_docs.html", context=_ctx(request))


@router.get("/crm", response_class=HTMLResponse)
def crm_redirect(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return RedirectResponse("/admin/integrations")


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


@router.get("/inbox", response_class=HTMLResponse)
def inbox_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "inbox.html", context=_ctx(request))


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "settings.html", context=_ctx(request))


@router.get("/approvals", response_class=HTMLResponse)
def approvals_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "approvals.html", context=_ctx(request))


# ─── Admin pages ──────────────────────────────────────────────────────


@router.get("/analytics", response_class=HTMLResponse)
def analytics_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "analytics.html", context=_ctx(request))


@router.get("/workflows", response_class=HTMLResponse)
def workflows_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "workflows.html", context=_ctx(request))


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


@router.get("/escalations", response_class=HTMLResponse)
def escalations_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "escalations.html", context=_ctx(request))


@router.get("/policies", response_class=HTMLResponse)
def policies_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "policies.html", context=_ctx(request))


@router.get("/timeline", response_class=HTMLResponse)
def timeline_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "timeline.html", context=_ctx(request))


# ─── /admin/api/ JSON endpoints ────────────────────────────────────────

import uuid


def _admin_api_dep(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    return tenant, db


@router.get("/api/integrations")
def api_integrations(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    connectors = db.query(NativeConnector).filter(NativeConnector.tenant_id == tenant.id).all()
    return {
        "native_connectors": [
            {
                "id": str(c.id),
                "provider": c.provider,
                "status": c.status,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in connectors
        ]
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
