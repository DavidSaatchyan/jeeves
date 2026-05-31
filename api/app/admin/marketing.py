from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Tenant
from ..core.events.schemas import CanonicalEvent
from ..core.workflows.registry import route_event
from .deps import get_admin_tenant
from .router import router


class _CreateCampaignBody(BaseModel):
    name: str
    trigger_type: str = "manual"
    trigger_config: dict = {}
    message_template: str = ""
    start_at: datetime | None = None
    end_at: datetime | None = None


class _CampaignTarget(BaseModel):
    patient_id: UUID
    wa_id: str
    patient_name: str
    phone_number_id: str
    access_token: str


@router.get("/api/campaigns")
def list_campaigns(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    status: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    from ..models import Campaign

    q = select(Campaign).where(Campaign.tenant_id == tenant.id)
    if status:
        q = q.where(Campaign.status == status)
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar() or 0
    rows = db.execute(q.order_by(Campaign.created_at.desc()).offset(offset).limit(limit)).scalars().all()
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "campaigns": [_campaign_to_dict(c) for c in rows],
    }


@router.post("/api/campaigns")
def create_campaign(
    body: _CreateCampaignBody,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    from ..models import Campaign
    from uuid import uuid4

    campaign = Campaign(
        id=uuid4(),
        tenant_id=tenant.id,
        name=body.name,
        trigger_type=body.trigger_type,
        trigger_config=body.trigger_config,
        message_template=body.message_template,
        status="draft",
        start_at=body.start_at,
        end_at=body.end_at,
    )
    db.add(campaign)
    db.commit()
    return _campaign_to_dict(campaign)


@router.post("/api/campaigns/{campaign_id}/launch")
async def launch_campaign(
    campaign_id: UUID,
    body: list[_CampaignTarget],
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    from ..models import Campaign

    campaign = db.get(Campaign, campaign_id)
    if not campaign or campaign.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status not in ("draft", "paused"):
        raise HTTPException(status_code=422, detail=f"Campaign status is {campaign.status}, cannot launch")

    launched = 0
    for target in body:
        event = CanonicalEvent(
            tenant_id=str(tenant.id),
            event_type="campaign_scheduled",
            event_source="marketing",
            entity_type="patient",
            entity_id=str(target.patient_id),
            payload={
                "patient_id": str(target.patient_id),
                "wa_id": target.wa_id,
                "patient_name": target.patient_name,
                "phone_number_id": target.phone_number_id,
                "access_token": target.access_token,
                "campaign_id": str(campaign_id),
                "campaign_name": campaign.name,
                "message_template": campaign.message_template,
            },
        )
        await route_event(event, db)
        launched += 1

    campaign.status = "active"
    db.commit()

    return {"ok": True, "launched": launched}


@router.post("/api/campaigns/{campaign_id}/pause")
def pause_campaign(
    campaign_id: UUID,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    from ..models import Campaign

    campaign = db.get(Campaign, campaign_id)
    if not campaign or campaign.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign.status = "paused"
    db.commit()
    return {"ok": True}


@router.get("/api/campaigns/{campaign_id}/analytics")
def campaign_analytics(
    campaign_id: UUID,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    from ..models import Campaign

    campaign = db.get(Campaign, campaign_id)
    if not campaign or campaign.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {
        "campaign_id": str(campaign_id),
        "status": campaign.status,
        "metrics": campaign.metrics or {},
    }


@router.get("/api/followups")
def list_followups(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    status: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    from ..models import Workflow

    q = select(Workflow).where(
        Workflow.tenant_id == tenant.id,
        Workflow.workflow_type == "followup",
    )
    if status:
        q = q.where(Workflow.status == status)
    total = db.execute(select(func.count()).select_from(q.subquery())).scalar() or 0
    rows = db.execute(q.order_by(Workflow.started_at.desc()).offset(offset).limit(limit)).scalars().all()
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "followups": [
            {
                "id": str(w.id),
                "patient_id": w.customer_id,
                "state": w.current_state,
                "status": w.status,
                "started_at": w.started_at.isoformat() if w.started_at else None,
            }
            for w in rows
        ],
    }


def _campaign_to_dict(c) -> dict:
    return {
        "id": str(c.id),
        "tenant_id": str(c.tenant_id),
        "name": c.name,
        "trigger_type": c.trigger_type,
        "status": c.status,
        "start_at": c.start_at.isoformat() if c.start_at else None,
        "end_at": c.end_at.isoformat() if c.end_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }
