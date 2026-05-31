from __future__ import annotations

from typing import Optional

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..auth.tokens import decode_token
from ..config import get_settings
from ..db import get_db
from ..models import Tenant
from .router import SESSION_COOKIE


def get_admin_tenant(
    request: Request,
    token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE),
    db: Session = Depends(get_db),
) -> Tenant:
    raw = token
    if not raw:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            raw = auth[7:]
    if not raw:
        raise HTTPException(status_code=status.HTTP_302_FOUND, headers={"Location": "/admin/login"})
    try:
        payload = decode_token(raw)
    except HTTPException:
        raise HTTPException(status_code=status.HTTP_302_FOUND, headers={"Location": "/admin/login"})
    if payload.get("kind") != "access":
        raise HTTPException(status_code=status.HTTP_302_FOUND, headers={"Location": "/admin/login"})
    import uuid
    tenant = db.get(Tenant, uuid.UUID(payload["sub"]))
    if not tenant:
        raise HTTPException(status_code=status.HTTP_302_FOUND, headers={"Location": "/admin/login"})
    return tenant


def _ctx(request: Request) -> dict:
    s = get_settings()
    base = s.public_base_url
    if not base or base == "http://localhost:8000":
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get("x-forwarded-host", request.url.netloc)
        base = f"{scheme}://{host}"
    return {"public_base_url": base}


def admin_api_dep(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    return tenant, db
