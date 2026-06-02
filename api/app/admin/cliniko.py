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


class ClinikoConfigUpdate(BaseModel):
    api_key: str
    shard: str = "au1"
    webhook_secret: str = ""


@router.get("/cliniko", response_class=HTMLResponse)
def cliniko_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    config = tenant.crm_config or {}
    provider = tenant.crm_provider or ""
    is_cliniko = provider == "cliniko"
    return templates.TemplateResponse(request, "cliniko_connections.html", {
        "request": request,
        "tenant_id": tenant.id,
        "connected": is_cliniko and bool(config.get("api_key")),
        "api_key": config.get("api_key", ""),
        "shard": config.get("shard", "au1"),
        "webhook_secret": config.get("webhook_secret", ""),
    })


@router.get("/api/cliniko/status")
def cliniko_status(tenant: Tenant = Depends(get_admin_tenant)):
    config = tenant.crm_config or {}
    provider = tenant.crm_provider or ""
    return {
        "connected": provider == "cliniko" and bool(config.get("api_key")),
        "provider": provider,
    }


@router.post("/api/cliniko/configure")
def configure_cliniko(
    data: ClinikoConfigUpdate,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_admin_tenant),
):
    tenant.crm_config = {
        "api_key": data.api_key,
        "shard": data.shard,
        "webhook_secret": data.webhook_secret,
        "user_agent": "Jeeves (devs@jeeves.ai)",
    }
    tenant.crm_provider = "cliniko"
    db.flush()
    db.commit()

    try:
        adapter = get_crm_adapter_for_tenant(tenant)
        if adapter and adapter.test_connection():
            return {"ok": True, "connected": True, "message": "Connected to Cliniko API"}
        return {"ok": True, "connected": False, "message": "Saved but connection failed — check API key and shard"}
    except Exception as e:
        return {"ok": True, "connected": False, "message": f"Saved but connection failed: {e}"}


@router.post("/api/cliniko/test")
def test_cliniko(tenant: Tenant = Depends(get_admin_tenant)):
    config = tenant.crm_config or {}
    if not config.get("api_key"):
        raise HTTPException(status_code=400, detail="Cliniko not configured")
    if tenant.crm_provider != "cliniko":
        raise HTTPException(status_code=400, detail="Cliniko is not the active provider")
    adapter = get_crm_adapter_for_tenant(tenant)
    if not adapter:
        raise HTTPException(status_code=400, detail="Could not create adapter")
    try:
        ok = adapter.test_connection()
        if ok:
            return {"ok": True, "message": "Connected to Cliniko API"}
        raise HTTPException(status_code=502, detail="Connection failed")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/api/cliniko/disconnect")
def disconnect_cliniko(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_admin_tenant),
):
    tenant.crm_config = {}
    tenant.crm_provider = "pabau"
    db.flush()
    db.commit()
    return {"ok": True}
