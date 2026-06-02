from __future__ import annotations

from fastapi import Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from sqlalchemy.orm import Session

from ..auth.tokens import issue_tokens
from ..db import get_db
from ..models import Tenant
from .deps import _ctx, get_admin_tenant
from .router import SESSION_COOKIE, router, templates


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def home(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return RedirectResponse(url="/admin/dashboard", status_code=status.HTTP_302_FOUND)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "dashboard.html", context=_ctx(request))


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
        key=SESSION_COOKIE,
        value=access,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=900,
        path="/admin",
    )
    return response


@router.post("/logout", response_class=HTMLResponse)
def admin_logout():
    response = RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key=SESSION_COOKIE, path="/admin")
    return response


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "settings.html", context=_ctx(request))


@router.get("/connections", response_class=HTMLResponse)
def connections_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "connections.html", context=_ctx(request))


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


# ── Channels API ─────────────────────────────────────────────


@router.get("/api/channels")
def api_channels(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    from ..channels.registry import list_all_configs
    return {"channels": list_all_configs(db, tenant.id)}


@router.post("/api/channels/{channel_type}")
def admin_save_channel(
    channel_type: str,
    body: dict,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    config = body.get("config", {})
    status = body.get("status", "active")
    from ..channels.registry import upsert_channel
    upsert_channel(db, tenant.id, channel_type, config, status)
    db.commit()
    return {"ok": True, "channel_type": channel_type, "status": status}
