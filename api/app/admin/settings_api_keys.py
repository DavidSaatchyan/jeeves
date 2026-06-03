from __future__ import annotations

import uuid as uuid_mod

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.activity_log import log_activity
from ..db import get_db
from ..models import ApiKey, Tenant, TeamMember
from .deps import get_admin_tenant, require_role
from .router import router


@router.get("/api/settings/api-keys")
def api_settings_list_keys(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    keys = db.execute(select(ApiKey).where(ApiKey.tenant_id == tenant.id).order_by(ApiKey.created_at.desc())).scalars().all()
    return {
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
    }


@router.post("/api/settings/api-keys")
def api_settings_create_key(
    body: dict,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    _: TeamMember = Depends(require_role("owner")),
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
    log_activity(db, tenant.id, tenant.email, "config_change", f"API key created: {name}", api_status="success")
    return {"ok": True, "raw_key": raw, "prefix": prefix, "name": name}


@router.delete("/api/settings/api-keys/{key_id}")
def api_settings_delete_key(
    key_id: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    _: TeamMember = Depends(require_role("owner")),
):
    try:
        kid = uuid_mod.UUID(key_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid key ID")
    key = db.execute(select(ApiKey).where(ApiKey.id == kid, ApiKey.tenant_id == tenant.id)).scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    db.delete(key)
    db.commit()
    log_activity(db, tenant.id, tenant.email, "config_change", f"API key revoked: {key.name}", api_status="success")
    return {"ok": True, "message": "API key revoked"}
