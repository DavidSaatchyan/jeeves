from __future__ import annotations

from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session


def upsert_objects(
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


def service_fields(item: dict[str, Any]) -> dict[str, Any]:
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


def practitioner_fields(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "display_name": item.get("display_name", item.get("first_name", "")),
        "title": item.get("title", ""),
        "designation": item.get("designation", ""),
        "description": item.get("description", item.get("notes", "")),
        "active": bool(item.get("active", True)),
        "raw_data": item,
    }


def clinic_fields(item: dict[str, Any]) -> dict[str, Any]:
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
