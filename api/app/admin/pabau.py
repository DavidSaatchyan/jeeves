from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from .deps import get_admin_tenant
from .router import templates, router
from ..models import Tenant


class PabauConfigUpdate(BaseModel):
    api_key: str
    company_id: str
    webhook_secret: str = ""


@router.get("/pabau", response_class=HTMLResponse)
def pabau_page(request: Request, tenant: Tenant = Depends(get_admin_tenant)):
    config = tenant.pabau_config or {}
    return templates.TemplateResponse(request, "pabau_connections.html", {
        "request": request,
        "tenant_id": tenant.id,
        "connected": bool(config.get("api_key") and config.get("company_id")),
        "api_key": config.get("api_key", ""),
        "company_id": config.get("company_id", ""),
    })


@router.get("/api/pabau/status")
def pabau_status(tenant: Tenant = Depends(get_admin_tenant)):
    config = tenant.pabau_config or {}
    return {"connected": bool(config.get("api_key") and config.get("company_id"))}


@router.post("/api/pabau/configure")
def configure_pabau(
    data: PabauConfigUpdate,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_admin_tenant),
):
    tenant.pabau_config = {
        "api_key": data.api_key,
        "company_id": data.company_id,
        "webhook_secret": data.webhook_secret,
    }
    db.flush()
    return {"ok": True}


@router.post("/api/pabau/test")
def test_pabau(tenant: Tenant = Depends(get_admin_tenant)):
    config = tenant.pabau_config or {}
    if not config.get("api_key") or not config.get("company_id"):
        raise HTTPException(status_code=400, detail="Pabau not configured")
    try:
        from ...integrations.pabau import PabauConnector
        adapter = PabauConnector(config)
        adapter._request("GET", "/patients", params={"limit": 1})
        return {"ok": True, "message": "Connected to Pabau API"}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/api/pabau/disconnect")
def disconnect_pabau(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_admin_tenant),
):
    tenant.pabau_config = {}
    db.flush()
    return {"ok": True}
