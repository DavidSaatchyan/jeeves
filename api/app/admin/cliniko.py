from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..integrations.resolver import get_crm_adapter_for_tenant
from .deps import get_admin_tenant
from .router import templates, router
from ..models import Tenant

_CLINIKO_SHARDS = ["au1", "au2", "au3", "au4", "au5", "eu1", "us1", "ca1", "uk1", "nz1", "sg1"]
_KNOWN_SHARDS = set(_CLINIKO_SHARDS)


class ClinikoConfigUpdate(BaseModel):
    api_key: str


def _try_shard(api_key: str, shard: str) -> bool:
    encoded = base64.b64encode(f"{api_key}:".encode()).decode()
    headers = {
        "Authorization": f"Basic {encoded}",
        "Accept": "application/json",
        "User-Agent": "Jeeves (devs@jeeves.ai)",
    }
    try:
        r = httpx.get(f"https://api.{shard}.cliniko.com/v1/practitioners", headers=headers, timeout=10)
        return r.status_code == 200
    except httpx.RequestError:
        return False


def _shard_from_key(api_key: str) -> str | None:
    """Extract shard from last 3 chars after dash (e.g. '...-au5' → 'au5')."""
    if len(api_key) >= 4 and api_key[-4] == "-":
        candidate = api_key[-3:]
        if candidate in _KNOWN_SHARDS:
            return candidate
    return None


def _discover_shard(api_key: str) -> str | None:
    shard = _shard_from_key(api_key)
    if shard and _try_shard(api_key, shard):
        return shard

    with ThreadPoolExecutor(max_workers=len(_CLINIKO_SHARDS)) as ex:
        future_map = {ex.submit(_try_shard, api_key, s): s for s in _CLINIKO_SHARDS}
        for f in as_completed(future_map):
            if f.result():
                return future_map[f]
    return None


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
    api_key = data.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="API Key is required")

    shard = _discover_shard(api_key)
    if not shard:
        return {"ok": True, "connected": False, "message": "Connection failed — check API key"}

    tenant.crm_config = {
        "api_key": api_key,
        "shard": shard,
        "user_agent": "Jeeves (devs@jeeves.ai)",
    }
    tenant.crm_provider = "cliniko"
    db.flush()
    db.commit()
    return {"ok": True, "connected": True, "message": "Connected to Cliniko API"}


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
