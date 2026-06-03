from __future__ import annotations

from datetime import datetime

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core import billing
from ..db import get_db
from ..models import FileRecord, Tenant
from .deps import get_admin_tenant
from .router import router


@router.get("/api/settings/billing")
def api_billing_details(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    from ..models import BillingPlan
    plan_row = db.execute(select(BillingPlan).where(BillingPlan.name == "free")).scalar_one_or_none()
    plan_info = {
        "resolved_limit": plan_row.resolved_limit if plan_row else 100,
        "storage_limit_mb": plan_row.storage_limit_mb if plan_row else 500,
        "agent_limit": plan_row.agent_limit if plan_row else 3,
        "price_usd": plan_row.price_usd if plan_row else 0,
    }

    resolved = tenant.resolved_count

    storage_used = db.execute(
        select(func.coalesce(func.sum(FileRecord.size_bytes), 0)).where(
            FileRecord.tenant_id == tenant.id
        )
    ).scalar() or 0

    agent_config = tenant.agent_config or {}
    agents_enabled = sum(
        1 for a in (agent_config.get("agents") or []) if a.get("enabled")
    )

    usage = billing.usage(tenant)

    return {
        "workspace_name": tenant.name,
        "workspace_email": tenant.email,
        "plan": "free",
        "plan_info": plan_info,
        "billing_enabled": tenant.is_active,
        "trial_ends": tenant.trial_ends.isoformat() if tenant.trial_ends else None,
        "trial_days_left": max(0, (tenant.trial_ends - datetime.utcnow()).days) if tenant.trial_ends else 0,
        "dialogs": {
            "used": resolved,
            "limit": plan_info.get("resolved_limit", 100),
        },
        "storage": {
            "used": storage_used,
            "limit": plan_info.get("storage_limit_mb", 500) * 1024 * 1024,
            "used_mb": round(storage_used / (1024 * 1024), 1),
            "limit_mb": plan_info.get("storage_limit_mb", 500),
        },
        "agents": {
            "used": agents_enabled,
            "limit": plan_info.get("agent_limit", 3),
        },
        "estimated_charge_usd": usage.get("estimated_charge_usd", 0),
        "overage_charge_usd": usage.get("overage_charge_usd", 0),
    }


