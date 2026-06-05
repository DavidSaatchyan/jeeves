from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.deps import get_current_tenant
from ..db import get_db
from ..integrations.cliniko import enrich_services_with_descriptions
from ..integrations.resolver import get_crm_adapter_for_tenant
from ..models import PmsClinic, PmsPractitioner, PmsService, Tenant
from ..rag import crm_indexer

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sync"])


class _SyncCrmIn(BaseModel):
    types: list[str] | None = None


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
            written = _upsert_objects(db, PmsService, tenant.id, services, "id", _service_fields)
            imported = crm_indexer.index_services(tenant.id, services, batch_id)
            result["services"] = {"imported": imported, "written_sql": written, "errors": []}
        except Exception as e:
            logger.error("CRM sync services failed: %s", e)
            result["services"] = {"imported": 0, "written_sql": 0, "errors": [str(e)[:500]]}

    # Practitioners
    if "practitioners" in requested:
        try:
            practitioners = adapter.get_practitioners()
            written = _upsert_objects(db, PmsPractitioner, tenant.id, practitioners, "id", _practitioner_fields)
            imported = crm_indexer.index_practitioners(tenant.id, practitioners, batch_id)
            result["practitioners"] = {"imported": imported, "written_sql": written, "errors": []}
        except Exception as e:
            logger.error("CRM sync practitioners failed: %s", e)
            result["practitioners"] = {"imported": 0, "written_sql": 0, "errors": [str(e)[:500]]}

    # Clinic
    if "clinic" in requested:
        try:
            businesses = adapter.get_businesses()
            clinic = businesses[0] if businesses else None
            items = [clinic] if clinic else []
            written = _upsert_objects(db, PmsClinic, tenant.id, items, "id", _clinic_fields)
            imported = crm_indexer.index_clinic(tenant.id, clinic, batch_id)
            result["clinic"] = {"imported": imported, "written_sql": written, "errors": []}
        except Exception as e:
            logger.error("CRM sync clinic failed: %s", e)
            result["clinic"] = {"imported": 0, "written_sql": 0, "errors": [str(e)[:500]]}

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


@router.post("/crm/reindex")
def reindex_crm_from_sql(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Reindex PMS data from SQL to Chroma without calling CRM API."""
    batch_id = f"pms-reindex-{tenant.id}-{datetime.now(timezone.utc).isoformat()}"
    result: dict[str, Any] = {}

    # Services
    try:
        rows = db.execute(
            select(PmsService).where(PmsService.tenant_id == tenant.id),
        ).scalars().all()
        items = [dict(r.raw_data or {}) | {"id": r.external_id, "name": r.name,
                "description": r.description, "price": r.price_cents,
                "duration_in_minutes": r.duration_minutes, "category": r.category,
                "telehealth_enabled": r.telehealth_enabled} for r in rows]
        imported = crm_indexer.index_services(tenant.id, items, batch_id)
        result["services"] = {"imported": imported, "from_sql": len(rows), "errors": []}
    except Exception as e:
        logger.error("Reindex services failed: %s", e)
        result["services"] = {"imported": 0, "from_sql": 0, "errors": [str(e)[:500]]}

    # Practitioners
    try:
        rows = db.execute(
            select(PmsPractitioner).where(PmsPractitioner.tenant_id == tenant.id),
        ).scalars().all()
        items = [dict(r.raw_data or {}) | {"id": r.external_id, "display_name": r.display_name,
                "title": r.title, "designation": r.designation,
                "description": r.description, "active": r.active} for r in rows]
        imported = crm_indexer.index_practitioners(tenant.id, items, batch_id)
        result["practitioners"] = {"imported": imported, "from_sql": len(rows), "errors": []}
    except Exception as e:
        logger.error("Reindex practitioners failed: %s", e)
        result["practitioners"] = {"imported": 0, "from_sql": 0, "errors": [str(e)[:500]]}

    # Clinic
    try:
        row = db.execute(
            select(PmsClinic).where(PmsClinic.tenant_id == tenant.id),
        ).scalars().first()
        item = None
        if row:
            item = dict(row.raw_data or {}) | {"id": row.external_id, "business_name": row.business_name}
        imported = crm_indexer.index_clinic(tenant.id, item, batch_id)
        result["clinic"] = {"imported": imported, "from_sql": 1 if row else 0, "errors": []}
    except Exception as e:
        logger.error("Reindex clinic failed: %s", e)
        result["clinic"] = {"imported": 0, "from_sql": 0, "errors": [str(e)[:500]]}

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
