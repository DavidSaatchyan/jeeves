from __future__ import annotations

from datetime import datetime

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db

from ..models import PolicySet, Tenant
from .deps import get_admin_tenant
from .router import router


@router.get("/api/policies")
def api_policies(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    ps = db.query(PolicySet).filter(PolicySet.tenant_id == tenant.id).first()
    if not ps:
        return {
            "retry": None,
            "communication": None,
            "escalation": None,
            "approval": None,
            "enabled_workflows": [],
        }
    return {
        "retry": ps.retry_policy,
        "communication": ps.communication_policy,
        "escalation": ps.escalation_policy,
        "approval": ps.approval_policy,
        "wismo": ps.wismo_policy or {},
        "enabled_workflows": ps.enabled_workflows or [],
    }


@router.put("/api/policies/{policy_type}")
def api_policies_update(
    policy_type: str,
    body: dict,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    ps = db.query(PolicySet).filter(PolicySet.tenant_id == tenant.id).first()
    if not ps:
        ps = PolicySet(tenant_id=tenant.id)
        db.add(ps)
    field_map = {
        "retry": "retry_policy",
        "communication": "communication_policy",
        "escalation": "escalation_policy",
        "approval": "approval_policy",
        "wismo": "wismo_policy",
        "enabled_workflows": "enabled_workflows",
    }
    field = field_map.get(policy_type)
    if not field:
        raise HTTPException(status_code=400, detail=f"Unknown policy type: {policy_type}")
    setattr(ps, field, body)
    ps.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "message": f"Policy '{policy_type}' updated"}
