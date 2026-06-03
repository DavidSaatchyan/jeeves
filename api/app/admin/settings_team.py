from __future__ import annotations

import uuid as uuid_mod

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..core.activity_log import log_activity
from ..db import get_db
from ..models import TeamMember, Tenant
from .deps import get_admin_tenant, require_role
from .router import router


@router.get("/api/settings/team")
def api_team_list(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    _: TeamMember = Depends(require_role("owner", "manager")),
):
    members = db.execute(
        select(TeamMember).where(TeamMember.tenant_id == tenant.id).order_by(TeamMember.created_at)
    ).scalars().all()
    return {
        "members": [
            {
                "id": str(m.id),
                "email": m.email,
                "name": m.name,
                "role": m.role,
                "invited_at": m.invited_at.isoformat() if m.invited_at else None,
                "accepted_at": m.accepted_at.isoformat() if m.accepted_at else None,
                "is_active": m.is_active,
            }
            for m in members
        ]
    }


@router.post("/api/settings/team/invite")
def api_team_invite(
    body: dict,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    _: TeamMember = Depends(require_role("owner", "manager")),
):
    email = (body.get("email") or "").strip().lower()
    role = (body.get("role") or "operator").strip().lower()
    name = (body.get("name") or "").strip()
    if role not in ("owner", "manager", "operator"):
        raise HTTPException(status_code=400, detail="Invalid role")
    existing = db.execute(
        select(TeamMember).where(TeamMember.tenant_id == tenant.id, TeamMember.email == email)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Member already invited")
    member = TeamMember(tenant_id=tenant.id, email=email, name=name, role=role)
    db.add(member)
    db.commit()
    log_activity(db, tenant.id, "👤 " + tenant.email, "config_change", f"Team member invited: {email} as {role}", extra_meta={"member_id": str(member.id)})
    return {"ok": True, "id": str(member.id)}


@router.put("/api/settings/team/{member_id}/role")
def api_team_update_role(
    member_id: str,
    body: dict,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    _: TeamMember = Depends(require_role("owner", "manager")),
):
    try:
        mid = uuid_mod.UUID(member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid member ID")
    member = db.execute(
        select(TeamMember).where(TeamMember.id == mid, TeamMember.tenant_id == tenant.id)
    ).scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    role = (body.get("role") or "").strip().lower()
    if role not in ("owner", "manager", "operator"):
        raise HTTPException(status_code=400, detail="Invalid role")
    member.role = role
    db.commit()
    log_activity(db, tenant.id, "👤 " + tenant.email, "config_change", f"Team member {member.email} role changed to {role}", extra_meta={"member_id": member_id})
    return {"ok": True}


@router.delete("/api/settings/team/{member_id}")
def api_team_remove(
    member_id: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    _: TeamMember = Depends(require_role("owner", "manager")),
):
    try:
        mid = uuid_mod.UUID(member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid member ID")
    member = db.execute(
        select(TeamMember).where(TeamMember.id == mid, TeamMember.tenant_id == tenant.id)
    ).scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    owner_count = db.execute(
        select(TeamMember).where(TeamMember.tenant_id == tenant.id, TeamMember.role == "owner", TeamMember.is_active)
    ).scalars().all()
    if member.role == "owner" and len(owner_count) <= 1:
        raise HTTPException(status_code=400, detail="Cannot remove the last owner")
    log_activity(db, tenant.id, "👤 " + tenant.email, "config_change", f"Team member removed: {member.email}", extra_meta={"member_id": member_id})
    db.delete(member)
    db.commit()
    return {"ok": True}


@router.post("/api/settings/team/{member_id}/resend")
def api_team_resend_invite(
    member_id: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    _: TeamMember = Depends(require_role("owner", "manager")),
):
    try:
        mid = uuid_mod.UUID(member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid member ID")
    member = db.execute(
        select(TeamMember).where(TeamMember.id == mid, TeamMember.tenant_id == tenant.id)
    ).scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return {"ok": True, "message": "Invite resent (placeholder — email would be sent here)"}
