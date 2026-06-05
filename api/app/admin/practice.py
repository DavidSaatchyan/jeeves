from __future__ import annotations

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse

from ..models import Tenant
from ..rag import count_chunks_by_source
from .deps import _ctx, get_admin_tenant
from .router import router, templates


@router.get("/practice", response_class=HTMLResponse)
def practice_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    chunks = count_chunks_by_source(tenant.id)
    config = tenant.crm_config or {}
    return templates.TemplateResponse(
        request, "practice.html",
        context=_ctx(request, tenant=tenant, chunks=chunks, last_sync_at=config.get("last_sync_at")),
    )
