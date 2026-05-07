"""Tenant API key management for REST integrations."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_
from sqlalchemy.orm import Session

from .auth import get_current_tenant
from .config import get_settings
from .db import get_db
from .models import ApiKey, Tenant

router = APIRouter(tags=["api-keys"])


def _hash_key(key: str) -> str:
    """HMAC-SHA256 with pepper to prevent rainbow table attacks even if DB is leaked."""
    pepper = get_settings().jwt_secret  # reuse as pepper
    return hmac.new(pepper.encode(), key.encode(), hashlib.sha256).hexdigest()


def _generate_key() -> str:
    return "sk_" + secrets.token_urlsafe(32)


@router.get("/api-keys")
def list_keys(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    rows = db.query(ApiKey).filter(ApiKey.tenant_id == tenant.id).order_by(ApiKey.created_at.desc()).all()
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "prefix": r.prefix,
            "created_at": r.created_at.isoformat(),
            "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
        }
        for r in rows
    ]


@router.post("/api-keys", status_code=201)
def create_key(body: dict, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    if len(name) > 128:
        raise HTTPException(400, "name too long (max 128 chars)")

    raw_key = _generate_key()
    key_id = uuid.uuid4()
    expires_days = body.get("expires_days")
    expires_at = None
    if expires_days and expires_days > 0:
        expires_at = datetime.utcnow() + timedelta(days=int(expires_days))

    key = ApiKey(
        id=key_id,
        tenant_id=tenant.id,
        name=name,
        key_hash=_hash_key(raw_key),
        prefix=raw_key[:12],
        expires_at=expires_at,
    )
    db.add(key)
    db.commit()

    return {
        "id": str(key_id),
        "name": name,
        "key": raw_key,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "warning": "Store this key securely. It will not be shown again.",
    }


@router.delete("/api-keys/{key_id}")
def revoke_key(key_id: str, tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    key = db.query(ApiKey).filter(and_(ApiKey.id == uuid.UUID(key_id), ApiKey.tenant_id == tenant.id)).first()
    if not key:
        raise HTTPException(404, "Key not found")
    db.delete(key)
    db.commit()
    return {"ok": True}
