from __future__ import annotations


from fastapi import Depends
from sqlalchemy.orm import Session

from ..db import get_db

from ..models import Tenant
from .deps import get_admin_tenant
from .router import router


@router.get("/api/policies")
def api_policies(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    return {
        "enabled_workflows": [],
    }


@router.put("/api/policies/enabled_workflows")
def api_policies_update_workflows(
    body: dict,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    return {"ok": True, "message": "Workflows updated (placeholder)"}


@router.put("/api/policies/{policy_type}")
def api_policies_update(
    policy_type: str,
    body: dict,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    return {"ok": True, "message": f"Policy '{policy_type}' updated (placeholder)"}
