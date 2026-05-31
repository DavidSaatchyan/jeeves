from __future__ import annotations

import uuid
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ApiKey, Tenant
from .router import SESSION_COOKIE
from .tokens import _hash_key, decode_token


def _get_client_ip(request: Request) -> str:
    return request.headers.get("x-forwarded-for", request.client.host or "unknown").split(",")[0].strip()


def get_current_tenant(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> Tenant:
    raw: Optional[str] = None
    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization.split(" ", 1)[1]
    if not raw:
        raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token or session")
    token = raw

    if token.startswith("sk_"):
        from datetime import datetime
        key_hash = _hash_key(token)
        api_key = db.query(ApiKey).filter(ApiKey.key_hash == key_hash).first()
        if not api_key:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
        if api_key.expires_at and api_key.expires_at < datetime.utcnow():
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API key has expired")
        api_key.last_used_at = datetime.utcnow()
        db.commit()
        tenant = db.get(Tenant, api_key.tenant_id)
        if not tenant:
            raise HTTPException(401, "Tenant not found")
        return tenant

    payload = decode_token(token)
    if payload.get("kind") != "access":
        raise HTTPException(401, "Wrong token kind")
    tenant = db.get(Tenant, uuid.UUID(payload["sub"]))
    if not tenant:
        raise HTTPException(401, "Tenant not found")
    return tenant
