"""Integration management API — manage native connectors (Shopify, Recharge, Stripe).

Credentials are stored Fernet-encrypted and are resolved per-tenant at workflow time.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .auth.deps import get_current_tenant
from .crypto import ConnectorError, decrypt, encrypt
from .db import get_db
from .models import NativeConnector, Tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])

_PROVIDERS = frozenset({"shopify"})


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
                "config_mask": _mask_creds(c.credentials) if c.status == "connected" else {},
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

    encrypted = encrypt(json.dumps(credentials))
    webhook_secret = body.get("webhook_secret", "")

    if existing:
        existing.credentials = encrypted
        existing.status = "connected"
        existing.updated_at = datetime.utcnow()
        meta = dict(existing.meta or {})
        if webhook_secret:
            meta["webhook_secret"] = webhook_secret
        existing.meta = meta
    else:
        meta = {}
        if webhook_secret:
            meta["webhook_secret"] = webhook_secret
        existing = NativeConnector(
            tenant_id=tenant.id,
            provider=provider,
            status="connected",
            credentials=encrypted,
            meta=meta,
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
    """Actually test the connection by making a lightweight API call."""
    provider = provider.lower()
    if provider not in _PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    from .integrations.credentials import get_credentials

    try:
        creds = get_credentials(tenant.id, provider, db)
    except ConnectorError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        if provider == "shopify":
            result = _test_shopify(creds)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

        return {"ok": True, "provider": provider, **result}
    except ConnectorError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("test_native failed for %s", provider)
        raise HTTPException(status_code=502, detail=f"Connection test failed: {e}")


def _test_shopify(creds: dict) -> dict:
    shop = creds.get("shop_domain", "")
    token = creds.get("access_token", "")
    if not shop or not token:
        raise ConnectorError(provider="shopify", operation="test", message="Missing shop_domain or access_token")

    url = f"https://{shop}/admin/api/2024-01/shop.json"
    headers = {"X-Shopify-Access-Token": token}
    try:
        r = httpx.get(url, headers=headers, timeout=10.0)
        if r.is_success:
            data = r.json().get("shop", {})
            return {"shop_name": data.get("name"), "shop_email": data.get("email")}
        raise ConnectorError(
            provider="shopify", operation="test", status_code=r.status_code,
            message=r.text[:200],
        )
    except httpx.RequestError as e:
        raise ConnectorError(provider="shopify", operation="test", message=str(e))
