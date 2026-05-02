"""CRM config + customer endpoints (FR-3, API spec /customer/{user_id})."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from . import crm, hubspot
from .auth import get_current_tenant
from .db import get_db
from .models import CRMActionLog, CRMConfig, Tenant
from .schemas import CRMConfigIn, CRMConfigOut, CRMTestOut, CustomerOut, UpdateCustomerIn

router = APIRouter(tags=["crm"])


@router.get("/crm/config", response_model=CRMConfigOut)
def get_cfg(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    cfg = db.get(CRMConfig, tenant.id)
    if not cfg:
        return CRMConfigOut()
    return CRMConfigOut(
        provider=cfg.provider or "custom_rest",
        read_url=cfg.read_url,
        write_url=cfg.write_url,
        headers=crm.mask_headers(cfg.headers or {}),
        read_mapping=cfg.read_mapping or {},
        write_mapping=cfg.write_mapping or {},
        capabilities=crm.capabilities(cfg),
        primary_identifier=cfg.primary_identifier or "email",
    )


@router.post("/crm/config", response_model=CRMConfigOut)
def save_cfg(
    body: CRMConfigIn,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    cfg = db.get(CRMConfig, tenant.id)
    if not cfg:
        cfg = CRMConfig(tenant_id=tenant.id)
        db.add(cfg)
    cfg.provider = body.provider or "custom_rest"
    cfg.read_url = body.read_url
    cfg.write_url = body.write_url
    cfg.headers = crm.merge_headers(cfg.headers or {}, body.headers)
    cfg.read_mapping = body.read_mapping
    cfg.write_mapping = body.write_mapping
    cfg.capabilities = crm.capabilities(cfg) | (body.capabilities or {})
    cfg.primary_identifier = body.primary_identifier or "email"
    db.commit()
    return CRMConfigOut(
        provider=cfg.provider,
        read_url=cfg.read_url,
        write_url=cfg.write_url,
        headers=crm.mask_headers(cfg.headers or {}),
        read_mapping=cfg.read_mapping or {},
        write_mapping=cfg.write_mapping or {},
        capabilities=crm.capabilities(cfg),
        primary_identifier=cfg.primary_identifier or "email",
    )


@router.post("/crm/test", response_model=CRMTestOut)
async def test_cfg(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    sample_user_id: str = "test",
):
    res = await crm.test_connection(db, tenant.id, sample_user_id)
    return CRMTestOut(**res)


@router.get("/crm/providers/status")
def provider_status(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    return {"hubspot": hubspot.status(db, tenant.id)}


@router.get("/crm/connect/hubspot")
def connect_hubspot(tenant: Tenant = Depends(get_current_tenant)):
    if not hubspot.enabled():
        raise HTTPException(400, "HubSpot OAuth credentials are not configured")
    return {"auth_url": hubspot.authorization_url(tenant.id)}


@router.get("/crm/oauth/hubspot/callback")
async def hubspot_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    if error:
        return RedirectResponse(url=f"/admin/integrations?hubspot=error&reason={error}")
    if not code or not state:
        return RedirectResponse(url="/admin/integrations?hubspot=missing_code")
    try:
        tenant_id = hubspot.decode_state(state)
        token_data = await hubspot.exchange_code(code)
        hubspot.save_connection(db, tenant_id, token_data)
    except Exception as e:
        return RedirectResponse(url=f"/admin/integrations?hubspot=error&reason={type(e).__name__}")
    return RedirectResponse(url="/admin/integrations?hubspot=connected")


@router.post("/crm/disconnect/hubspot")
def disconnect_hubspot(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    hubspot.disconnect(db, tenant.id)
    return {"ok": True}


@router.get("/crm/actions")
def action_logs(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
    limit: int = 50,
):
    rows = (
        db.query(CRMActionLog)
        .filter(CRMActionLog.tenant_id == tenant.id)
        .order_by(CRMActionLog.created_at.desc())
        .limit(min(limit, 200))
        .all()
    )
    return [
        {
            "created_at": r.created_at.isoformat(),
            "user_id": r.user_id,
            "action": r.action,
            "status": r.status,
            "latency_ms": r.latency_ms,
            "error": r.error,
        }
        for r in rows
    ]


@router.get("/customer/{user_id}", response_model=CustomerOut)
async def get_customer(
    user_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    try:
        data = await crm.read_customer(db, tenant.id, user_id)
    except Exception as e:
        raise HTTPException(502, f"CRM read failed: {e}")
    return CustomerOut(
        tariff=data.get("tariff"),
        accounts_count=data.get("accounts_count"),
        views_trend=data.get("views_trend"),
        raw=data.get("raw"),
    )


@router.patch("/customer/{user_id}")
async def update_customer(
    user_id: str,
    body: UpdateCustomerIn,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    try:
        await crm.write_customer(db, tenant.id, user_id, body.model_dump(exclude_none=True))
    except Exception as e:
        raise HTTPException(502, f"CRM write failed: {e}")
    return {"ok": True}
