from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..integrations.cliniko import enrich_services_with_descriptions
from ..integrations.resolver import get_crm_adapter_for_tenant
from ..models import PmsClinic, PmsPractitioner, PmsService, Tenant
from ..rag import crm_indexer
from ..shared.pms_fields import clinic_fields, practitioner_fields, service_fields, upsert_objects

logger = logging.getLogger(__name__)


def _get_last_sync(tenant: Tenant) -> str | None:
    config = tenant.crm_config or {}
    return config.get("last_sync_at")


def _save_sync_result(tenant: Tenant, result: dict[str, Any], db: Session) -> None:
    now = datetime.now(timezone.utc)
    config = dict(tenant.crm_config or {})
    config["last_sync_at"] = now.isoformat()
    sync_counts: dict[str, Any] = config.get("sync_counts", {})
    for type_key in ("services", "practitioners", "clinic"):
        if type_key in result and not result[type_key].get("errors"):
            sync_counts[type_key] = {
                "count": result[type_key]["imported"],
                "last_sync": now.isoformat(),
            }
    config["sync_counts"] = sync_counts
    tenant.crm_config = config
    db.commit()


def poll_crm_changes(tenant_id: str | UUID) -> dict[str, Any]:
    """Incremental sync: fetch only records updated since last sync.

    Can be called from BackgroundTasks, cron, or scheduler.
    Returns per-type counts and errors.
    """
    db = SessionLocal()
    try:
        tenant = db.execute(select(Tenant).where(Tenant.id == tenant_id)).scalar_one_or_none()
        if not tenant:
            return {"error": "Tenant not found"}

        adapter = get_crm_adapter_for_tenant(tenant.id)
        if not adapter:
            return {"error": "No CRM adapter configured"}

        last_sync = _get_last_sync(tenant)
        batch_id = f"crm-poll-{tenant.id}-{datetime.now(timezone.utc).isoformat()}"
        result: dict[str, Any] = {}

        # Services (incremental)
        try:
            billable_items = adapter.get_billable_items(item_type="Service", updated_since=last_sync)
            appointment_types = adapter.get_appointment_types(updated_since=last_sync)
            links = adapter.get_appointment_type_billable_items()
            services = enrich_services_with_descriptions(billable_items, appointment_types, links)
            written = upsert_objects(db, PmsService, tenant.id, services, "id", service_fields)
            imported = crm_indexer.index_services(tenant.id, services, batch_id)
            result["services"] = {"imported": imported, "written_sql": written, "errors": []}
        except Exception as e:
            logger.error("CRM poll services failed: %s", e)
            result["services"] = {"imported": 0, "written_sql": 0, "errors": [str(e)[:500]]}

        # Practitioners (incremental)
        try:
            practitioners = adapter.get_practitioners()
            written = upsert_objects(db, PmsPractitioner, tenant.id, practitioners, "id", practitioner_fields)
            imported = crm_indexer.index_practitioners(tenant.id, practitioners, batch_id)
            result["practitioners"] = {"imported": imported, "written_sql": written, "errors": []}
        except Exception as e:
            logger.error("CRM poll practitioners failed: %s", e)
            result["practitioners"] = {"imported": 0, "written_sql": 0, "errors": [str(e)[:500]]}

        # Clinic (always full resync — small data)
        try:
            businesses = adapter.get_businesses()
            clinic = businesses[0] if businesses else None
            items = [clinic] if clinic else []
            written = upsert_objects(db, PmsClinic, tenant.id, items, "id", clinic_fields)
            imported = crm_indexer.index_clinic(tenant.id, clinic, batch_id)
            result["clinic"] = {"imported": imported, "written_sql": written, "errors": []}
        except Exception as e:
            logger.error("CRM poll clinic failed: %s", e)
            result["clinic"] = {"imported": 0, "written_sql": 0, "errors": [str(e)[:500]]}

        _save_sync_result(tenant, result, db)
        result["batch_id"] = batch_id
        return result

    finally:
        db.close()
