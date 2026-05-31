from __future__ import annotations

import json
import logging
from datetime import datetime

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..crypto import ConnectorError, decrypt, encrypt
from ..db import get_db
from ..models import CrmConnection, NativeConnector, Tenant
from .deps import _ctx, get_admin_tenant
from .router import router

logger = logging.getLogger(__name__)

_CONNECTOR_FIELDS: dict[str, list[str]] = {
    "zoho": ["client_id", "client_secret", "refresh_token", "accounts_domain", "api_domain"],
    "hubspot": ["access_token", "portal_id"],
    "custom_api": ["base_url", "auth_type", "auth_credentials", "endpoint_mapping"],
}
_WEBHOOK_EVENTS: dict[str, list[str]] = {
    "zoho": ["Contacts.create", "Contacts.edit", "Appointments__s.create", "Appointments__s.edit"],
    "hubspot": ["contact.creation", "contact.deletion", "meeting.created", "meeting.deleted"],
    "custom_api": ["*"],
}


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


def _mask_crm_config(config: dict) -> dict:
    masked = {}
    for k, v in config.items():
        if isinstance(v, str) and any(s in k.lower() for s in ("secret", "token", "key", "password")):
            masked[k] = v[:6] + "••••" if len(v) > 6 else "••••"
        else:
            masked[k] = v
    return masked


@router.get("/api/integrations")
def api_integrations(
    request: Request,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    ctx = _ctx(request)
    base = ctx.get("public_base_url", "").rstrip("/")
    webhook_base = f"{base}/integrations/webhooks" if base else None

    connectors = db.query(NativeConnector).filter(NativeConnector.tenant_id == tenant.id).all()
    result = []
    for c in connectors:
        status = "disconnected"
        if c and c.status == "connected":
            try:
                creds = json.loads(decrypt(c.credentials))
                required = _CONNECTOR_FIELDS.get(c.provider, [])
                status = "connected" if all(creds.get(f) for f in required) else "disconnected"
            except Exception:
                status = "disconnected"

        result.append({
            "id": str(c.id),
            "provider": c.provider,
            "status": status,
            "config_mask": _mask_creds(c.credentials) if status == "connected" else {},
            "has_webhook_secret": bool((c.meta or {}).get("webhook_secret")) if c else False,
            "webhook_url": f"{webhook_base}/{c.provider}" if webhook_base else None,
            "webhook_events": _WEBHOOK_EVENTS.get(c.provider, []),
            "connector_fields": _CONNECTOR_FIELDS.get(c.provider, []),
            "created_at": c.created_at.isoformat() if c and c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c and c.updated_at else None,
        })

    crm_result = []
    for c in db.query(CrmConnection).filter(CrmConnection.tenant_id == tenant.id).all():
        cfg = dict(c.config or {})
        required = _CONNECTOR_FIELDS.get(c.provider, [])
        status = "connected" if (c.status == "connected" and all(cfg.get(f) for f in required)) else "disconnected"
        wh_url = f"{webhook_base}/custom/{tenant.id}" if (webhook_base and c.provider == "custom_api") else (f"{webhook_base}/{c.provider}" if webhook_base else None)
        crm_result.append({
            "id": str(c.id),
            "provider": c.provider,
            "status": status,
            "config_mask": _mask_crm_config(cfg) if status == "connected" else {},
            "has_webhook_secret": bool(c.webhook_secret),
            "webhook_url": wh_url,
            "webhook_events": _WEBHOOK_EVENTS.get(c.provider, []),
            "connector_fields": _CONNECTOR_FIELDS.get(c.provider, []),
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        })

    return {
        "native_connectors": result,
        "crm_connections": crm_result,
        "webhook_base_url": webhook_base,
        "providers": list(_CONNECTOR_FIELDS.keys()),
    }


@router.post("/api/integrations/native", status_code=201)
def admin_connect_native(
    body: dict,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    provider = body.get("provider", "").lower()
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


@router.delete("/api/integrations/native/{provider}")
def admin_disconnect_native(
    provider: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    provider = provider.lower()
    connector = db.query(NativeConnector).filter(
        NativeConnector.tenant_id == tenant.id,
        NativeConnector.provider == provider,
    ).first()
    if not connector:
        raise HTTPException(status_code=404, detail=f"Connector '{provider}' not found")
    db.delete(connector)
    db.commit()
    return {"ok": True, "provider": provider, "status": "disconnected"}


@router.post("/api/integrations/native/{provider}/test")
def admin_test_native(
    provider: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    provider = provider.lower()
    from ..integrations.credentials import get_credentials
    try:
        creds = get_credentials(tenant.id, provider, db)
    except ConnectorError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "provider": provider, "message": "Connection stored (test TBD for this provider)"}


# ── CRM connection CRUD ──────────────────────────────────────


@router.get("/api/crm")
def api_crm_connections(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    conns = db.query(CrmConnection).filter(CrmConnection.tenant_id == tenant.id).all()
    return {
        "connections": [
            {
                "id": str(c.id),
                "provider": c.provider,
                "status": c.status,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                "last_sync_at": c.last_sync_at.isoformat() if c.last_sync_at else None,
            }
            for c in conns
        ]
    }


@router.post("/api/crm", status_code=201)
def admin_connect_crm(
    body: dict,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    provider = body.get("provider", "").lower()
    config = body.get("config", body.get("credentials", {}))
    if not config or not isinstance(config, dict):
        raise HTTPException(status_code=400, detail="Config required")
    if provider not in _CONNECTOR_FIELDS:
        raise HTTPException(status_code=400, detail=f"Unsupported CRM provider: {provider}")

    existing = db.query(CrmConnection).filter(
        CrmConnection.tenant_id == tenant.id,
        CrmConnection.provider == provider,
    ).first()

    webhook_secret = body.get("webhook_secret", "")

    if existing:
        existing.config = config
        existing.status = "connected"
        existing.updated_at = datetime.utcnow()
        if webhook_secret:
            existing.webhook_secret = webhook_secret
    else:
        existing = CrmConnection(
            tenant_id=tenant.id,
            provider=provider,
            status="connected",
            config=config,
            webhook_secret=webhook_secret or None,
        )
        db.add(existing)

    db.commit()
    return {"ok": True, "provider": provider, "status": "connected"}


@router.delete("/api/crm/{provider}")
def admin_disconnect_crm(
    provider: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    provider = provider.lower()
    conn = db.query(CrmConnection).filter(
        CrmConnection.tenant_id == tenant.id,
        CrmConnection.provider == provider,
    ).first()
    if not conn:
        raise HTTPException(status_code=404, detail=f"CRM '{provider}' not found")
    db.delete(conn)
    db.commit()
    return {"ok": True, "provider": provider, "status": "disconnected"}


@router.post("/api/crm/{provider}/test")
def admin_test_crm(
    provider: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    provider = provider.lower()
    from ..integrations.credentials import get_credentials
    try:
        creds = get_credentials(tenant.id, provider, db)
    except ConnectorError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "provider": provider, "message": f"{provider} credentials resolved"}


@router.post("/api/crm/{provider}/sync")
def admin_sync_crm(
    provider: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    provider = provider.lower()
    from ..integrations.credentials import get_credentials
    try:
        config = get_credentials(tenant.id, provider, db)
    except ConnectorError as e:
        raise HTTPException(status_code=400, detail=str(e))

    from ..integrations.crm import get_crm_adapter
    adapter = get_crm_adapter(provider, config)

    try:
        contacts = adapter.list_contacts()
        appts = adapter.list_appointments()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Sync failed: {e}")

    conn = db.query(CrmConnection).filter(
        CrmConnection.tenant_id == tenant.id,
        CrmConnection.provider == provider,
    ).first()
    if conn:
        conn.last_sync_at = datetime.utcnow()
        db.commit()

    return {
        "ok": True,
        "provider": provider,
        "contacts_count": len(contacts),
        "appointments_count": len(appts),
    }
