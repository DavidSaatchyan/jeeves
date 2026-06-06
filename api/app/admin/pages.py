from __future__ import annotations

from fastapi import Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from ..auth.tokens import issue_tokens
from ..config import get_settings
from ..db import get_db
from ..models import Tenant
from .deps import _ctx, get_admin_tenant
from ..shared.constants import SESSION_COOKIE
from .router import router, templates


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def home(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return RedirectResponse(url="/admin/dashboard", status_code=status.HTTP_302_FOUND)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "dashboard.html", context=_ctx(request, tenant=tenant))


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", context=_ctx(request))


@router.post("/login", response_class=HTMLResponse)
async def admin_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db=Depends(get_db),
):
    from passlib.context import CryptContext

    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

    tenant = db.execute(select(Tenant).where(Tenant.email == email)).scalar_one_or_none()
    pw = password.encode("utf-8")[:72].decode("utf-8", errors="ignore")
    if not tenant or not pwd_ctx.verify(pw, tenant.hashed_password):
        return RedirectResponse(
            url="/admin/login?error=invalid",
            status_code=status.HTTP_302_FOUND,
        )

    access, refresh = issue_tokens(tenant.id)
    response = RedirectResponse(url="/admin", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=access,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=get_settings().access_token_ttl_minutes * 60,
        path="/admin",
    )
    response.set_cookie(
        key="jeeves_refresh",
        value=refresh,
        httponly=False,
        secure=False,
        samesite="lax",
        path="/admin",
    )
    return response


@router.post("/logout", response_class=HTMLResponse)
def admin_logout():
    response = RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key=SESSION_COOKIE, path="/admin")
    response.delete_cookie(key="jeeves_refresh", path="/admin")
    return response


# ── Settings pages ─────────────────────────────────────────────

@router.get("/settings/team", response_class=HTMLResponse)
def settings_team_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "settings_team.html", context=_ctx(request, tenant=tenant))


@router.get("/settings/billing", response_class=HTMLResponse)
def settings_billing_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "settings_billing.html", context=_ctx(request, tenant=tenant))


@router.get("/settings/logs", response_class=HTMLResponse)
def settings_logs_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "settings_logs.html", context=_ctx(request, tenant=tenant))


# ── Legacy redirects ───────────────────────────────────────────

@router.get("/settings", response_class=HTMLResponse)
def settings_legacy_redirect():
    return RedirectResponse(url="/admin/settings/team", status_code=status.HTTP_302_FOUND)


# ── Legacy pages ──────────────────────────────────────────────

@router.get("/knowledge", response_class=HTMLResponse)
def knowledge_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    from ..rag.engine import count_chunks_by_source
    chunks = count_chunks_by_source(tenant.id)
    ctx = _ctx(request, tenant=tenant, chunks=chunks)
    ctx["tenant_id"] = str(tenant.id)
    return templates.TemplateResponse(request, "knowledge.html", context=ctx)



