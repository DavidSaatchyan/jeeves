from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth.deps import get_current_tenant
from ..db import get_db
from ..integrations.cliniko import enrich_services_with_descriptions
from ..integrations.resolver import get_crm_adapter_for_tenant
from ..models import Tenant
from ..rag import crm_indexer

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sync"])


class _SyncCrmIn(BaseModel):
    types: list[str] | None = None


@router.post("/crm")
def sync_crm(
    body: _SyncCrmIn | None = None,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Полная синхронизация CRM → KB для указанных типов (или всех)."""
    adapter = get_crm_adapter_for_tenant(tenant)
    if not adapter:
        raise HTTPException(400, "No CRM adapter configured for this tenant")

    requested = body.types if body and body.types is not None else ["services", "practitioners", "clinic"]
    result: dict[str, Any] = {}
    batch_id = f"crm-sync-{tenant.id}-{datetime.now(timezone.utc).isoformat()}"

    # Services
    if "services" in requested:
        try:
            billable_items = adapter.get_billable_items(item_type="Service")
            appointment_types = adapter.get_appointment_types()
            links = adapter.get_appointment_type_billable_items()
            services = enrich_services_with_descriptions(billable_items, appointment_types, links)
            imported = crm_indexer.index_services(tenant.id, services, batch_id)
            result["services"] = {"imported": imported, "updated": 0, "errors": []}
        except Exception as e:
            logger.error("CRM sync services failed: %s", e)
            result["services"] = {"imported": 0, "updated": 0, "errors": [str(e)[:500]]}

    # Practitioners
    if "practitioners" in requested:
        try:
            practitioners = adapter.get_practitioners()
            imported = crm_indexer.index_practitioners(tenant.id, practitioners, batch_id)
            result["practitioners"] = {"imported": imported, "updated": 0, "errors": []}
        except Exception as e:
            logger.error("CRM sync practitioners failed: %s", e)
            result["practitioners"] = {"imported": 0, "updated": 0, "errors": [str(e)[:500]]}

    # Clinic
    if "clinic" in requested:
        try:
            businesses = adapter.get_businesses()
            clinic = businesses[0] if businesses else None
            imported = crm_indexer.index_clinic(tenant.id, clinic, batch_id)
            result["clinic"] = {"imported": imported, "updated": 0, "errors": []}
        except Exception as e:
            logger.error("CRM sync clinic failed: %s", e)
            result["clinic"] = {"imported": 0, "updated": 0, "errors": [str(e)[:500]]}

    # Save last_sync_at to crm_config
    now = datetime.now(timezone.utc)
    config = dict(tenant.crm_config or {})
    config["last_sync_at"] = now.isoformat()
    sync_counts: dict[str, Any] = config.get("sync_counts", {})
    for type_key in ("services", "practitioners", "clinic"):
        if type_key in result and not result[type_key]["errors"]:
            sync_counts[type_key] = {
                "count": result[type_key]["imported"],
                "last_sync": now.isoformat(),
            }
    config["sync_counts"] = sync_counts
    tenant.crm_config = config
    db.commit()

    result["batch_id"] = batch_id
    return result


@router.get("/crm/status")
def sync_crm_status(
    tenant: Tenant = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Статус последней синхронизации CRM."""
    config = tenant.crm_config or {}
    last_sync_at = config.get("last_sync_at")
    sync_counts = config.get("sync_counts", {})
    return {
        "last_sync_at": last_sync_at,
        "crm_provider": tenant.crm_provider,
        "services": sync_counts.get("services", {"count": 0, "last_sync": None}),
        "practitioners": sync_counts.get("practitioners", {"count": 0, "last_sync": None}),
        "clinic": sync_counts.get("clinic", {"count": 0, "last_sync": None}),
    }
