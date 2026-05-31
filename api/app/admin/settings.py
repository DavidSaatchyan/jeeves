from __future__ import annotations

import uuid as uuid_mod

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db

from .. import billing
from ..models import ApiKey, Tenant
from .deps import get_admin_tenant
from .router import router


@router.get("/api/settings")
def api_settings(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    keys = db.query(ApiKey).filter(ApiKey.tenant_id == tenant.id).order_by(ApiKey.created_at.desc()).all()
    return {
        "workspace": {
            "name": tenant.name,
            "email": tenant.email,
            "plan": "free",
            "trial_ends": tenant.trial_ends.isoformat() if tenant.trial_ends else None,
            "is_active": tenant.is_active,
        },
        "api_keys": [
            {
                "id": str(k.id),
                "name": k.name,
                "prefix": k.prefix,
                "created_at": k.created_at.isoformat() if k.created_at else None,
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                "expires_at": k.expires_at.isoformat() if k.expires_at else None,
            }
            for k in keys
        ],
        "notifications": {
            "escalation_alerts": True,
            "approval_alerts": True,
            "workflow_failure_alerts": True,
            "daily_summary": False,
        },
        "billing": billing.usage(tenant),
    }


@router.put("/api/settings")
def api_settings_update(
    body: dict,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    return {"ok": True, "message": "Settings updated (placeholder)"}


@router.post("/api/settings/api-keys")
def api_settings_create_key(
    body: dict,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    import hashlib
    import secrets
    name = body.get("name", "default")
    raw = "jev_sk_" + secrets.token_hex(24)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    prefix = raw[:12]
    key = ApiKey(tenant_id=tenant.id, name=name, key_hash=hashed, prefix=prefix)
    db.add(key)
    db.commit()
    return {"ok": True, "raw_key": raw, "prefix": prefix, "name": name}


@router.delete("/api/settings/api-keys/{key_id}")
def api_settings_delete_key(
    key_id: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    try:
        kid = uuid_mod.UUID(key_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid key ID")
    key = db.query(ApiKey).filter(ApiKey.id == kid, ApiKey.tenant_id == tenant.id).first()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    db.delete(key)
    db.commit()
    return {"ok": True, "message": "API key revoked"}
