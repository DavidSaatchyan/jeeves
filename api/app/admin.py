"""Admin Dashboard (FR-6) — server-rendered Jinja2 pages.

DEFAULT: minimal SSR to avoid shipping a separate SPA. Pages call the same
JSON API endpoints via fetch() from inline scripts.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .config import get_settings

router = APIRouter(prefix="/admin", tags=["admin"])

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _ctx(request: Request) -> dict:
    s = get_settings()
    return {"request": request, "public_base_url": s.public_base_url}


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("dashboard.html", _ctx(request))


@router.get("/login", response_class=HTMLResponse)
def login(request: Request):
    return templates.TemplateResponse("login.html", _ctx(request))


@router.get("/knowledge", response_class=HTMLResponse)
def knowledge(request: Request):
    return templates.TemplateResponse("knowledge.html", _ctx(request))


@router.get("/integrations", response_class=HTMLResponse)
def integrations_page(request: Request):
    return templates.TemplateResponse("integrations.html", _ctx(request))


@router.get("/logs", response_class=HTMLResponse)
def logs_page(request: Request):
    return templates.TemplateResponse("logs.html", _ctx(request))


@router.get("/channels", response_class=HTMLResponse)
def channels_page(request: Request):
    return templates.TemplateResponse("channels.html", _ctx(request))


@router.get("/widget-preview", response_class=HTMLResponse)
def widget_preview(request: Request):
    return templates.TemplateResponse("widget_preview.html", _ctx(request))


@router.get("/proactive", response_class=HTMLResponse)
def proactive_page(request: Request):
    return templates.TemplateResponse("proactive.html", _ctx(request))


@router.get("/billing", response_class=HTMLResponse)
def billing_page(request: Request):
    return templates.TemplateResponse("billing.html", _ctx(request))


@router.get("/tools", response_class=HTMLResponse)
def tools_page(request: Request):
    return templates.TemplateResponse("tools.html", _ctx(request))


# Old /admin/crm URL redirects to /admin/integrations
@router.get("/crm", response_class=HTMLResponse)
def crm_redirect(request: Request):
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/admin/integrations")
