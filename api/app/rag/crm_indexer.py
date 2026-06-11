from __future__ import annotations

import logging
from typing import Any, Callable
from uuid import UUID

from sqlalchemy import select

from . import chunking
from .batch import batch_add, batch_delete_ids
from .client import _collection, embed_batch
from .maintenance import _all_chunks
from ..models import HmsClinic, HmsPractitioner, HmsService

logger = logging.getLogger(__name__)


def _extract_service_sections(svc: dict[str, Any]) -> list[tuple[str, str]]:
    name = svc.get("name", "")
    lines: list[str] = [f"Name: {name}"]

    price = svc.get("price")
    if price is not None:
        dollars = float(price) / 100 if isinstance(price, int) else float(price)
        lines.append(f"Pricing: ${dollars:.2f}")
    duration = svc.get("duration_in_minutes")
    if duration is not None:
        lines.append(f"Duration: {int(duration)} minutes")
    category = svc.get("category", "")
    if category:
        lines.append(f"Category: {category}")
    description = svc.get("description", "")
    if description:
        lines.append(f"Description: {description}")
    telehealth = svc.get("telehealth_enabled")
    if telehealth is not None:
        lines.append(f"Telehealth: {'Yes' if telehealth else 'No'}")
    online = svc.get("online_booking_enabled", svc.get("online_bookable"))
    if online is not None:
        lines.append(f"Online booking: {'Yes' if online else 'No'}")
    item_code = svc.get("item_code", "")
    if item_code:
        lines.append(f"Code: {item_code}")

    section_label = f"Service: {name}" if name else "Service"
    return [(section_label, "\n".join(lines))]


def _extract_practitioner_sections(prac: dict[str, Any]) -> list[tuple[str, str]]:
    import re
    display = prac.get("display_name", "")
    if display:
        full_name = display
    else:
        first = prac.get("first_name", "")
        last = prac.get("last_name", "")
        full_name = f"{first} {last}".strip() or ""

    normalized = re.sub(r'^(Mr\.?|Mrs\.?|Ms\.?|Dr\.?|Prof\.?)\s+', '', full_name, flags=re.IGNORECASE)

    lines: list[str] = [f"Name: {normalized}"]
    if full_name.lower() != normalized.lower():
        lines.append(f"Display Name: {full_name}")

    title = prac.get("title", "")
    if title:
        lines.append(f"Title: {title}")
    designation = prac.get("designation", "")
    if designation:
        lines.append(f"Specialty: {designation}")
    description = prac.get("description", "")
    if description:
        lines.append(f"Description: {description}")
    lines.append(f"Accepting new patients: {'Yes' if prac.get('active', True) else 'No'}")

    section_label = f"Practitioner: {normalized}" if normalized else "Practitioner"
    return [(section_label, "\n".join(lines))]


def _extract_clinic_sections(clinic: dict[str, Any]) -> list[tuple[str, str]]:
    lines: list[str] = []
    name = clinic.get("business_name", clinic.get("name", ""))
    if name:
        lines.append(f"Clinic Name: {name}")

    for label, key in [("Address", "address"), ("City", "city"), ("State", "state"), ("Postcode", "postcode"), ("Country", "country")]:
        val = clinic.get(key, "")
        if val:
            lines.append(f"{label}: {val}")

    address = ", ".join(filter(None, [
        clinic.get("address", ""),
        clinic.get("city", ""),
        clinic.get("state", ""),
        clinic.get("postcode", ""),
        clinic.get("country", ""),
    ]))
    if address:
        lines.append(f"Full Address: {address}")

    for label, key in [("Phone", "phone"), ("Email", "email"), ("Website", "website"), ("Timezone", "timezone")]:
        val = clinic.get(key, "")
        if val:
            lines.append(f"{label}: {val}")

    additional = clinic.get("additional_info", "")
    if additional:
        lines.append(f"Additional info: {additional}")

    section_label = f"Clinic: {name}" if name else "Clinic"
    return [(section_label, "\n".join(lines))]


def _delete_by_type_and_batch(
    tenant_id: UUID | str,
    doc_type: str,
    batch_id: str,
) -> int:
    col = _collection(tenant_id)
    try:
        before = col.count()
        col.delete(where={"$and": [{"source": "hms"}, {"type": doc_type}]})
        after = col.count()
        removed = before - after
        if removed:
            logger.info("crm_indexer: deleted %d %s docs", removed, doc_type)
        return removed
    except Exception as e:
        logger.warning("crm_indexer: delete error for %s: %s", doc_type, e)
        return 0


def _index_type(
    tenant_id: UUID | str,
    items: list[dict[str, Any]],
    batch_id: str,
    doc_type: str,
    extract_sections_fn: Callable[[dict[str, Any]], list[tuple[str, str]]],
    id_field: str = "id",
) -> int:
    if not items:
        return 0

    _delete_by_type_and_batch(tenant_id, doc_type, batch_id)

    texts: list[str] = []
    metadatas: list[dict] = []
    ids: list[str] = []

    for i, item in enumerate(items):
        item_id = str(item.get(id_field, "") or f"unknown-{i}")
        sections = extract_sections_fn(item)
        filename = f"hms-{doc_type}-{item_id}.txt"
        chunks = chunking.build_chunks_from_sections(sections, filename)
        name = str(item.get("name", item.get("display_name", item.get("business_name", ""))))

        for c in chunks:
            chunk_id = f"hms-{doc_type}-{batch_id}-{item_id}-{c.chunk_hash}"
            meta: dict[str, Any] = {
                "source": "hms",
                "folder_id": "",
                "type": doc_type,
                f"{doc_type}_id": item_id,
                "name": name,
                "import_batch": batch_id,
                "file_id": f"hms-{batch_id}",
                "filename": filename,
                "section": c.section,
                "chunk_hash": c.chunk_hash,
                "char_start": c.char_start,
                "char_end": c.char_end,
            }
            if doc_type == "service":
                price = item.get("price")
                meta["price"] = str(price) if price is not None else ""
                meta["category"] = str(item.get("category", ""))
            elif doc_type == "practitioner":
                meta["designation"] = str(item.get("designation", ""))
                meta["active"] = bool(item.get("active", True))
            texts.append(c.text)
            metadatas.append(meta)
            ids.append(chunk_id)

    if not texts:
        return 0

    embeddings = embed_batch(texts)
    col = _collection(tenant_id)
    batch_add(col, ids, embeddings, texts, metadatas)
    logger.info("crm_indexer: indexed %d chunks for %d %s items (batch=%s)", len(texts), len(items), doc_type, batch_id)
    return len(texts)


def index_services(
    tenant_id: UUID | str,
    services: list[dict[str, Any]],
    batch_id: str,
) -> int:
    return _index_type(tenant_id, services, batch_id, "service", _extract_service_sections)


def index_practitioners(
    tenant_id: UUID | str,
    practitioners: list[dict[str, Any]],
    batch_id: str,
) -> int:
    return _index_type(tenant_id, practitioners, batch_id, "practitioner", _extract_practitioner_sections)


def index_clinic(
    tenant_id: UUID | str,
    clinic: dict[str, Any] | None,
    batch_id: str,
) -> int:
    items = [clinic] if clinic else []
    return _index_type(tenant_id, items, batch_id, "clinic", _extract_clinic_sections)


def delete_by_type_and_batch(
    tenant_id: UUID | str,
    doc_type: str,
    batch_id: str,
) -> int:
    return _delete_by_type_and_batch(tenant_id, doc_type, batch_id)


def cleanup_orphans(tenant_id: UUID | str, db_session: Any) -> dict[str, int]:
    """Remove HMS chunks from Chroma whose external_id no longer exists in SQL DB."""
    col = _collection(tenant_id)
    ids, metas = _all_chunks(tenant_id)
    if not ids:
        return {"total": 0, "removed": 0, "errors": 0}

    # Gather active external IDs from SQL
    active: dict[str, set[str]] = {"service": set(), "practitioner": set(), "clinic": set()}
    try:
        for row in db_session.execute(select(HmsService.external_id).where(HmsService.tenant_id == tenant_id)).all():
            active["service"].add(str(row[0]))
        for row in db_session.execute(select(HmsPractitioner.external_id).where(HmsPractitioner.tenant_id == tenant_id)).all():
            active["practitioner"].add(str(row[0]))
        for row in db_session.execute(select(HmsClinic.external_id).where(HmsClinic.tenant_id == tenant_id)).all():
            active["clinic"].add(str(row[0]))
    except Exception as e:
        logger.error("cleanup_orphans: failed to query SQL: %s", e)
        return {"total": 0, "removed": 0, "errors": 1}

    to_delete: list[str] = []
    for cid, meta in zip(ids, metas):
        src = (meta or {}).get("source", "")
        if src != "hms":
            continue
        dtype = (meta or {}).get("type", "")
        eid = (meta or {}).get(f"{dtype}_id", "")
        if dtype in active and eid not in active[dtype]:
            to_delete.append(cid)

    if to_delete:
        batch_delete_ids(col, to_delete)
        logger.info("cleanup_orphans: removed %d orphan HMS chunks", len(to_delete))

    return {"total": len(ids), "removed": len(to_delete), "errors": 0}



