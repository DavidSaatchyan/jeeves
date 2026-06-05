from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..integrations.cliniko import enrich_services_with_descriptions
from ..integrations.resolver import get_crm_adapter_for_tenant
from ..models import PmsClinic, PmsPractitioner, PmsService, Tenant
from ..rag import crm_indexer

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


def _upsert_objects(
    db: Session,
    model: type,
    tenant_id: Any,
    items: list[dict[str, Any]],
    id_field: str,
    field_map_fn: Callable[[dict[str, Any]], dict[str, Any]],
) -> int:
    if not items:
        return 0
    external_ids = [str(item[id_field]) for item in items if item.get(id_field)]
    existing = {
        r.external_id: r
        for r in db.execute(
            select(model).where(model.tenant_id == tenant_id, model.external_id.in_(external_ids)),
        ).scalars().all()
    }
    count = 0
    for item in items:
        eid = str(item.get(id_field, ""))
        if not eid:
            continue
        fields = field_map_fn(item)
        if eid in existing:
            for k, v in fields.items():
                setattr(existing[eid], k, v)
        else:
            db.add(model(tenant_id=tenant_id, external_id=eid, **fields))
        count += 1
    db.flush()
    return count


def _service_fields(item: dict[str, Any]) -> dict[str, Any]:
    price_raw = item.get("price", 0)
    price_cents = price_raw if isinstance(price_raw, int) else int(float(price_raw) * 100)
    return {
        "name": item.get("name", ""),
        "description": item.get("description", ""),
        "price_cents": price_cents,
        "duration_minutes": item.get("duration_in_minutes"),
        "category": item.get("category", ""),
        "telehealth_enabled": bool(item.get("telehealth_enabled", False)),
        "online_bookable": bool(item.get("online_booking_enabled", item.get("online_bookable", True))),
        "raw_data": item,
    }


def _practitioner_fields(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "display_name": item.get("display_name", item.get("first_name", "")),
        "title": item.get("title", ""),
        "designation": item.get("designation", ""),
        "description": item.get("description", ""),
        "active": bool(item.get("active", True)),
        "raw_data": item,
    }


def _clinic_fields(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "business_name": item.get("business_name", item.get("name", "")),
        "address": item.get("address", ""),
        "city": item.get("city", ""),
        "state": item.get("state", ""),
        "postcode": item.get("postcode", ""),
        "country": item.get("country", ""),
        "phone": item.get("phone", ""),
        "email": item.get("email", ""),
        "website": item.get("website", ""),
        "timezone": item.get("timezone", ""),
        "raw_data": item,
    }


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
            written = _upsert_objects(db, PmsService, tenant.id, services, "id", _service_fields)
            imported = crm_indexer.index_services(tenant.id, services, batch_id)
            result["services"] = {"imported": imported, "written_sql": written, "errors": []}
        except Exception as e:
            logger.error("CRM poll services failed: %s", e)
            result["services"] = {"imported": 0, "written_sql": 0, "errors": [str(e)[:500]]}

        # Practitioners (incremental)
        try:
            practitioners = adapter.get_practitioners()
            written = _upsert_objects(db, PmsPractitioner, tenant.id, practitioners, "id", _practitioner_fields)
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
            written = _upsert_objects(db, PmsClinic, tenant.id, items, "id", _clinic_fields)
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
