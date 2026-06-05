from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.tokens import decode_token
from ..config import get_settings
from ..db import SessionLocal, get_db
from ..models import TeamMember, Tenant
from ..shared.constants import SESSION_COOKIE


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
    tenant = db.get(Tenant, uuid.UUID(payload["sub"]))
    if not tenant:
        raise HTTPException(status_code=status.HTTP_302_FOUND, headers={"Location": "/admin/login"})
    return tenant


def get_current_team_member(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
) -> TeamMember:
    member = db.execute(select(TeamMember).where(
        TeamMember.tenant_id == tenant.id,
        TeamMember.email == tenant.email,
        TeamMember.is_active,
    )).scalar_one_or_none()
    if not member:
        member = TeamMember(tenant_id=tenant.id, email=tenant.email, name=tenant.name, role="owner", accepted_at=datetime.utcnow())
        db.add(member)
        db.commit()
        db.refresh(member)
    return member


def require_role(*roles: str):
    def _checker(member: TeamMember = Depends(get_current_team_member)) -> TeamMember:
        if member.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return member
    return _checker


def _ctx(request: Request, tenant: Tenant | None = None, **kwargs: Any) -> dict:
    s = get_settings()
    base = s.public_base_url
    if not base or base == "http://localhost:8000":
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get("x-forwarded-host", request.url.netloc)
        base = f"{scheme}://{host}"
    role = _resolve_role(tenant) if tenant else "owner"
    ctx: dict[str, Any] = {"public_base_url": base, "tenant_role": role}
    ctx.update(kwargs)
    return ctx


def _resolve_role(tenant: Tenant) -> str:
    db: Session | None = None
    try:
        db = SessionLocal()
        member = db.execute(select(TeamMember).where(
            TeamMember.tenant_id == tenant.id,
            TeamMember.email == tenant.email,
        )).scalar_one_or_none()
        return member.role if member else "owner"
    except Exception:
        return "owner"
    finally:
        if db is not None:
            db.close()




