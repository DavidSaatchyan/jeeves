"""Admin Dashboard (FR-6) — server-rendered Jinja2 pages.

DEFAULT: minimal SSR to avoid shipping a separate SPA. Pages call the same
JSON API endpoints via fetch() from inline scripts.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .auth import decode_token, get_current_tenant, issue_tokens
from .config import get_settings
from .db import get_db
from .models import Tenant

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
    if not tenant or not pwd_ctx.verify(password, tenant.hashed_password):
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
