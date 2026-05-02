"""Proactive engine config endpoints (FR-7)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .auth import get_current_tenant
from .db import get_db
from .models import ProactiveMetric, Tenant
from .schemas import ProactiveConfigIn

router = APIRouter(prefix="/proactive", tags=["proactive"])


@router.get("/config")
def get_cfg(tenant: Tenant = Depends(get_current_tenant), db: Session = Depends(get_db)):
    p = db.get(ProactiveMetric, tenant.id)
    if not p:
        return {"metric_url": None, "threshold": 30}
    return {"metric_url": p.metric_url, "threshold": p.threshold}


@router.post("/config")
def save_cfg(
    body: ProactiveConfigIn,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    p = db.get(ProactiveMetric, tenant.id)
    if not p:
        p = ProactiveMetric(tenant_id=tenant.id)
        db.add(p)
    p.metric_url = body.metric_url
    p.threshold = body.threshold
    db.commit()
    return {"ok": True}
