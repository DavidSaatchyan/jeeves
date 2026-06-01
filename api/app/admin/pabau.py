from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..integrations.resolver import get_crm_adapter_for_tenant
from .deps import get_admin_tenant
from .router import templates, router
from ..models import Tenant


class CrmConfigUpdate(BaseModel):
    api_key: str
    company_id: str = ""
    webhook_secret: str = ""
    shard: str = ""
    crm_provider: str = "pabau"


@router.get("/pabau", response_class=HTMLResponse)
def pabau_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    config = tenant.crm_config or {}
    provider = tenant.crm_provider or "pabau"
    return templates.TemplateResponse(request, "pabau_connections.html", {
        "request": request,
        "tenant_id": tenant.id,
        "connected": bool(config.get("api_key")),
        "api_key": config.get("api_key", ""),
        "company_id": config.get("company_id", ""),
        "webhook_secret": config.get("webhook_secret", ""),
        "crm_provider": provider,
    })


@router.get("/api/crm/status")
def crm_status(tenant: Tenant = Depends(get_admin_tenant)):
    config = tenant.crm_config or {}
    return {
        "connected": bool(config.get("api_key")),
        "provider": tenant.crm_provider or "pabau",
    }


@router.post("/api/crm/configure")
def configure_crm(
    data: CrmConfigUpdate,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_admin_tenant),
):
    tenant.crm_config = {
        "api_key": data.api_key,
        "company_id": data.company_id,
        "webhook_secret": data.webhook_secret,
        "shard": data.shard,
    }
    tenant.crm_provider = data.crm_provider
    db.flush()
    return {"ok": True}


@router.post("/api/crm/test")
def test_crm(tenant: Tenant = Depends(get_admin_tenant)):
    config = tenant.crm_config or {}
    provider = tenant.crm_provider or "pabau"
    if not config.get("api_key"):
        raise HTTPException(status_code=400, detail=f"{provider.title()} not configured")
    adapter = get_crm_adapter_for_tenant(tenant)
    if not adapter:
        raise HTTPException(status_code=400, detail="Could not create adapter")
    try:
        ok = adapter.test_connection()
        if ok:
            return {"ok": True, "message": f"Connected to {provider.title()} API"}
        raise HTTPException(status_code=502, detail="Connection failed")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/api/crm/disconnect")
def disconnect_crm(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_admin_tenant),
):
    tenant.crm_config = {}
    db.flush()
    return {"ok": True}
