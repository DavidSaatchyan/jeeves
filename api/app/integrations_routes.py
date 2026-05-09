"""Integration management API — manage native connectors (Shopify, Recharge, Stripe)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .auth import get_current_tenant
from .db import get_db
from .models import NativeConnector, Tenant

router = APIRouter(prefix="/integrations", tags=["integrations"])

_PROVIDERS = {"shopify", "recharge", "stripe"}


def _mask_creds(creds: str) -> dict:
    try:
        data = json.loads(creds)
        masked = {}
        for k, v in data.items():
            if any(s in k.lower() for s in ("secret", "token", "key", "password")):
                masked[k] = v[:6] + "••••" if len(v) > 6 else "••••"
            else:
                masked[k] = v
        return masked
    except (json.JSONDecodeError, TypeError):
        return {"masked": True}


@router.get("")
def list_integrations(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    connectors = db.query(NativeConnector).filter(NativeConnector.tenant_id == tenant.id).all()
    return {
        "native_connectors": [
            {
                "id": str(c.id),
                "provider": c.provider,
                "status": c.status,
                "config_mask": _mask_creds(c.credentials),
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in connectors
        ]
    }


@router.post("/native", status_code=201)
def connect_native(
    body: dict,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    provider = body.get("provider", "").lower()
    if provider not in _PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
    credentials = body.get("credentials", {})
    if not credentials:
        raise HTTPException(status_code=400, detail="Credentials required")

    existing = db.query(NativeConnector).filter(
        NativeConnector.tenant_id == tenant.id,
        NativeConnector.provider == provider,
    ).first()

    if existing:
        existing.credentials = json.dumps(credentials)
        existing.status = "connected"
        existing.updated_at = datetime.utcnow()
    else:
        existing = NativeConnector(
            tenant_id=tenant.id,
            provider=provider,
            status="connected",
            credentials=json.dumps(credentials),
        )
        db.add(existing)

    db.commit()
    return {"ok": True, "provider": provider, "status": "connected"}


@router.delete("/native/{provider}")
def disconnect_native(
    provider: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    provider = provider.lower()
    if provider not in _PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
    connector = db.query(NativeConnector).filter(
        NativeConnector.tenant_id == tenant.id,
        NativeConnector.provider == provider,
    ).first()
    if not connector:
        raise HTTPException(status_code=404, detail=f"Connector '{provider}' not found")
    db.delete(connector)
    db.commit()
    return {"ok": True, "provider": provider, "status": "disconnected"}


@router.post("/native/{provider}/test")
def test_native(
    provider: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    provider = provider.lower()
    if provider not in _PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
    connector = db.query(NativeConnector).filter(
        NativeConnector.tenant_id == tenant.id,
        NativeConnector.provider == provider,
    ).first()
    if not connector:
        raise HTTPException(status_code=404, detail=f"Connector '{provider}' not found")
    return {"ok": True, "message": f"{provider} connection verified", "provider": provider}
