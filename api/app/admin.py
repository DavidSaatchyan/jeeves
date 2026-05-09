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
    Communication,
    Escalation,
    NativeConnector,
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
    return templates.TemplateResponse(request, "dashboard.html", context=_ctx(request))


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


# ─── Missing page routes ──────────────────────────────────────────────


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
    }
