from __future__ import annotations

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse

from ..models import Tenant
from .deps import _ctx, get_admin_tenant
from .router import router, templates


@router.get("/practice", response_class=HTMLResponse)
def practice_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    return templates.TemplateResponse(request, "practice.html", context=_ctx(request, tenant=tenant))
