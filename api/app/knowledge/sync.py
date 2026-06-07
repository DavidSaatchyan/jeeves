from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..auth.deps import get_current_tenant
from ..config import get_settings
from ..db import get_db
from ..integrations.hms import HmsConnector
from ..integrations.resolver import get_crm_adapter_for_tenant, get_hms_adapter_for_tenant
from ..shared.timer import timed
from ..models import HmsClinic, HmsPractitioner, HmsService, Tenant
from ..rag import crm_indexer
from ..rag.crm_indexer import cleanup_orphans as hms_cleanup_orphans
from ..shared.hms_schemas import validate_hms_records
from ..shared.hms_fields import clinic_fields, practitioner_fields, service_fields, upsert_objects

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sync"])


class _SyncCrmIn(BaseModel):
    types: list[str] | None = None


def _save_sync_config(tenant: Tenant, result: dict[str, Any], db: Session) -> None:
    now = datetime.now(timezone.utc)
    config = dict(tenant.crm_config or {})
    config["last_sync_at"] = now.isoformat()
    sync_counts: dict[str, Any] = config.get("sync_counts", {})
    config["prev_sync_counts"] = dict(sync_counts)
    sync_errors: dict[str, Any] = {}
    for type_key in ("services", "practitioners", "clinic"):
        if type_key not in result:
            continue
        if result[type_key].get("errors"):
            sync_errors[type_key] = result[type_key]["errors"][:500]
        else:
            sync_counts[type_key] = {
                "count": result[type_key]["imported"],
                "last_sync": now.isoformat(),
            }
    config["sync_counts"] = sync_counts
    config["sync_errors"] = sync_errors
    tenant.crm_config = config
    db.commit()


def _sync_services_hms(hms: HmsConnector, tenant: Tenant, updated_since: str | None, batch_id: str, db: Session) -> dict[str, Any]:
    try:
        services = hms.fetch_services(updated_since=updated_since)
        validate_hms_records(hms.provider, "service", services)
        written = upsert_objects(db, HmsService, tenant.id, services, "id", service_fields)
        imported = crm_indexer.index_services(tenant.id, services, batch_id)
        return {"imported": imported, "written_sql": written, "errors": []}
    except Exception as e:
        logger.error("CRM sync services failed: %s", e)
        return {"imported": 0, "written_sql": 0, "errors": [str(e)[:500]]}


def _sync_practitioners_hms(hms: HmsConnector, tenant: Tenant, batch_id: str, db: Session) -> dict[str, Any]:
    try:
        practitioners = hms.fetch_practitioners()
        validate_hms_records(hms.provider, "practitioner", practitioners)
        written = upsert_objects(db, HmsPractitioner, tenant.id, practitioners, "id", practitioner_fields)
        imported = crm_indexer.index_practitioners(tenant.id, practitioners, batch_id)
        return {"imported": imported, "written_sql": written, "errors": []}
    except Exception as e:
        logger.error("CRM sync practitioners failed: %s", e)
        return {"imported": 0, "written_sql": 0, "errors": [str(e)[:500]]}


def _sync_clinic_hms(hms: HmsConnector, tenant: Tenant, batch_id: str, db: Session) -> dict[str, Any]:
    try:
        clinics = hms.fetch_clinics()
        validate_hms_records(hms.provider, "clinic", clinics)
        clinic = clinics[0] if clinics else None
        items = [clinic] if clinic else []
        written = upsert_objects(db, HmsClinic, tenant.id, items, "id", clinic_fields)
        imported = crm_indexer.index_clinic(tenant.id, clinic, batch_id)
        return {"imported": imported, "written_sql": written, "errors": []}
    except Exception as e:
        logger.error("CRM sync clinic failed: %s", e)
        return {"imported": 0, "written_sql": 0, "errors": [str(e)[:500]]}


@timed("sync.crm")
@router.post("/crm")
def sync_crm(
    body: _SyncCrmIn | None = None,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Полная синхронизация CRM → KB для указанных типов (или всех)."""
    settings = get_settings()

    if settings.feature_use_hms_connector:
        hms = get_hms_adapter_for_tenant(tenant)
        if not hms:
            raise HTTPException(400, "No CRM/HMS adapter configured for this tenant")
        requested = body.types if body and body.types is not None else ["services", "practitioners", "clinic"]
        result: dict[str, Any] = {}
        batch_id = f"crm-sync-{tenant.id}-{datetime.now(timezone.utc).isoformat()}"

        if "services" in requested:
            result["services"] = _sync_services_hms(hms, tenant, None, batch_id, db)
        if "practitioners" in requested:
            result["practitioners"] = _sync_practitioners_hms(hms, tenant, batch_id, db)
        if "clinic" in requested:
            result["clinic"] = _sync_clinic_hms(hms, tenant, batch_id, db)

        _save_sync_config(tenant, result, db)
        result["batch_id"] = batch_id

        try:
            orphan_result = hms_cleanup_orphans(tenant.id, db)
            result["orphans_cleaned"] = orphan_result.get("removed", 0)
        except Exception as e:
            logger.error("CRM sync orphan cleanup failed: %s", e)
            result["orphans_cleaned"] = -1

        return result

    # Legacy path via AbstractCrmConnector
    adapter = get_crm_adapter_for_tenant(tenant)
    if not adapter:
        raise HTTPException(400, "No CRM adapter configured for this tenant")

    from ..integrations.cliniko import enrich_services_with_descriptions

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
            written = upsert_objects(db, HmsService, tenant.id, services, "id", service_fields)
            imported = crm_indexer.index_services(tenant.id, services, batch_id)
            result["services"] = {"imported": imported, "written_sql": written, "errors": []}
        except Exception as e:
            logger.error("CRM sync services failed: %s", e)
            result["services"] = {"imported": 0, "written_sql": 0, "errors": [str(e)[:500]]}

    # Practitioners
    if "practitioners" in requested:
        try:
            practitioners = adapter.get_practitioners()
            written = upsert_objects(db, HmsPractitioner, tenant.id, practitioners, "id", practitioner_fields)
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
            written = upsert_objects(db, HmsClinic, tenant.id, items, "id", clinic_fields)
            imported = crm_indexer.index_clinic(tenant.id, clinic, batch_id)
            result["clinic"] = {"imported": imported, "written_sql": written, "errors": []}
        except Exception as e:
            logger.error("CRM sync clinic failed: %s", e)
            result["clinic"] = {"imported": 0, "written_sql": 0, "errors": [str(e)[:500]]}

    _save_sync_config(tenant, result, db)
    result["batch_id"] = batch_id

    # Clean up orphans after sync
    try:
        orphan_result = hms_cleanup_orphans(tenant.id, db)
        result["orphans_cleaned"] = orphan_result.get("removed", 0)
    except Exception as e:
        logger.error("CRM sync orphan cleanup failed: %s", e)
        result["orphans_cleaned"] = -1

    return result


@router.post("/crm/reindex")
def reindex_crm_from_sql(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Reindex HMS data from SQL to Chroma without calling CRM API."""
    batch_id = f"hms-reindex-{tenant.id}-{datetime.now(timezone.utc).isoformat()}"
    result: dict[str, Any] = {}

    # Services
    try:
        rows = db.execute(
            select(HmsService).where(HmsService.tenant_id == tenant.id),
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
            select(HmsPractitioner).where(HmsPractitioner.tenant_id == tenant.id),
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
            select(HmsClinic).where(HmsClinic.tenant_id == tenant.id),
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


@router.post("/crm/orphans")
def cleanup_crm_orphans(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    """Remove HMS chunks from Chroma whose external_id no longer exists in SQL DB."""
    try:
        result = hms_cleanup_orphans(tenant.id, db)
        return result
    except Exception as e:
        raise HTTPException(500, f"Orphan cleanup failed: {e}")


@router.get("/crm/status")
def sync_crm_status(
    tenant: Tenant = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Статус последней синхронизации CRM."""
    config = tenant.crm_config or {}
    last_sync_at = config.get("last_sync_at")
    sync_counts = config.get("sync_counts", {})
    prev_counts = config.get("prev_sync_counts", {})
    sync_errors = config.get("sync_errors", {})
    diff: dict[str, int] = {}
    for key in ("services", "practitioners", "clinic"):
        current = sync_counts.get(key, {}).get("count", 0)
        previous = prev_counts.get(key, {}).get("count", 0)
        diff[key] = current - previous
    return {
        "last_sync_at": last_sync_at,
        "crm_provider": tenant.crm_provider,
        "services": sync_counts.get("services", {"count": 0, "last_sync": None}),
        "practitioners": sync_counts.get("practitioners", {"count": 0, "last_sync": None}),
        "clinic": sync_counts.get("clinic", {"count": 0, "last_sync": None}),
        "errors": sync_errors,
        "diff": diff,
    }


_PREVIEW_MODEL: dict[str, type] = {
    "services": HmsService,
    "practitioners": HmsPractitioner,
    "clinic": HmsClinic,
}

_PREVIEW_FIELDS: dict[str, list[str]] = {
    "services": ["name", "description", "price_cents", "duration_minutes", "category", "telehealth_enabled", "online_bookable"],
    "practitioners": ["display_name", "title", "designation", "description", "active"],
    "clinic": ["business_name", "address", "city", "state", "postcode", "country", "phone", "email", "website"],
}

_SORT_FIELDS: dict[str, str] = {
    "services": "name",
    "practitioners": "display_name",
    "clinic": "business_name",
}

_SEARCH_FIELDS: dict[str, list[str]] = {
    "services": ["name", "description", "category"],
    "practitioners": ["display_name", "title", "designation", "description"],
    "clinic": ["business_name", "address", "city", "state", "postcode", "country", "phone", "email"],
}


@router.get("/crm/counts")
def crm_counts(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    """Return total record count per entity type."""
    result: dict[str, int] = {}
    for key, model in _PREVIEW_MODEL.items():
        count = db.execute(
            select(func.count(model.id)).where(model.tenant_id == tenant.id),
        ).scalar() or 0
        result[key] = count
    return result


@router.get("/crm/{type}/table")
def crm_table(
    type: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    sort: str | None = Query(None),
    order: str = Query("asc"),
    search: str | None = Query(None),
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Paginated table view of synced records with sort and search."""
    model = _PREVIEW_MODEL.get(type)
    if not model:
        raise HTTPException(404, f"Unknown type: {type}")

    fields = _PREVIEW_FIELDS.get(type, [])
    default_sort = _SORT_FIELDS.get(type, fields[0] if fields else "id")
    sort_field = sort if sort in fields or sort in ("id", "updated_at", "created_at") else default_sort

    base = select(model).where(model.tenant_id == tenant.id)

    if search:
        searchable = _SEARCH_FIELDS.get(type, [])
        filters = [getattr(model, f).ilike(f"%{search}%") for f in searchable if hasattr(model, f)]
        if filters:
            base = base.where(or_(*filters))

    total: int = db.execute(select(func.count()).select_from(base.subquery())).scalar() or 0

    sort_col = getattr(model, sort_field, None)
    if sort_col is not None:
        base = base.order_by(sort_col.asc() if order == "asc" else sort_col.desc(), model.created_at)

    rows = db.execute(base.offset((page - 1) * per_page).limit(per_page)).scalars().all()

    result_rows: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {"id": row.external_id, "updated_at": row.updated_at.isoformat() if row.updated_at else None}
        for f in fields:
            item[f] = getattr(row, f, None)
        result_rows.append(item)

    return {"rows": result_rows, "total": total, "page": page, "per_page": per_page}


@router.get("/crm/{type}")
def preview_crm_type(
    type: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """List synced records for a given type (services, practitioners, clinic)."""
    model = _PREVIEW_MODEL.get(type)
    if not model:
        raise HTTPException(404, f"Unknown type: {type}")
    fields = _PREVIEW_FIELDS.get(type, [])
    rows = db.execute(
        select(model).where(model.tenant_id == tenant.id).order_by(model.created_at),
    ).scalars().all()
    result: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {"id": row.external_id, "updated_at": row.updated_at.isoformat() if row.updated_at else None}
        for f in fields:
            item[f] = getattr(row, f, None)
        result.append(item)
    return result
