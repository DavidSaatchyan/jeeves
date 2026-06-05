from __future__ import annotations

import logging
from typing import Any, Callable
from uuid import UUID

from . import chunking
from .client import _collection, embed_batch

logger = logging.getLogger(__name__)


def _extract_service_sections(svc: dict[str, Any]) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = [("Name", svc.get("name", ""))]
    price = svc.get("price")
    if price is not None:
        dollars = float(price) / 100 if isinstance(price, int) else float(price)
        sections.append(("Pricing", f"${dollars:.2f}"))
    duration = svc.get("duration_in_minutes")
    if duration is not None:
        sections.append(("Duration", f"{int(duration)} minutes"))
    category = svc.get("category", "")
    if category:
        sections.append(("Category", category))
    description = svc.get("description", "")
    if description:
        sections.append(("Description", description))
    telehealth = svc.get("telehealth_enabled")
    if telehealth is not None:
        sections.append(("Telehealth", "Yes" if telehealth else "No"))
    online = svc.get("online_booking_enabled", svc.get("online_bookable"))
    if online is not None:
        sections.append(("Online booking", "Yes" if online else "No"))
    item_code = svc.get("item_code", "")
    if item_code:
        sections.append(("Code", item_code))
    return sections


def _extract_practitioner_sections(prac: dict[str, Any]) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = [
        ("Name", prac.get("display_name", prac.get("first_name", ""))),
    ]
    title = prac.get("title", "")
    if title:
        sections.append(("Title", title))
    designation = prac.get("designation", "")
    if designation:
        sections.append(("Specialty", designation))
    description = prac.get("description", "")
    if description:
        sections.append(("Description", description))
    sections.append(
        ("Accepting new patients", "Yes" if prac.get("active", True) else "No"),
    )
    return sections


def _extract_clinic_sections(clinic: dict[str, Any]) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = [
        ("Clinic", clinic.get("business_name", clinic.get("name", ""))),
    ]
    address = ", ".join(filter(None, [
        clinic.get("address", ""),
        clinic.get("city", ""),
        clinic.get("state", ""),
        clinic.get("postcode", ""),
        clinic.get("country", ""),
    ]))
    if address:
        sections.append(("Address", address))
    phone = clinic.get("phone", "")
    if phone:
        sections.append(("Phone", phone))
    email = clinic.get("email", "")
    if email:
        sections.append(("Email", email))
    website = clinic.get("website", "")
    if website:
        sections.append(("Website", website))
    timezone = clinic.get("timezone", "")
    if timezone:
        sections.append(("Timezone", timezone))
    additional = clinic.get("additional_info", "")
    if additional:
        sections.append(("Additional info", additional))
    return sections


def _delete_by_type_and_batch(
    tenant_id: UUID | str,
    doc_type: str,
    batch_id: str,
) -> int:
    col = _collection(tenant_id)
    try:
        before = col.count()
        col.delete(where={"$and": [{"source": "pms"}, {"type": doc_type}]})
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
        filename = f"pms-{doc_type}-{item_id}.txt"
        chunks = chunking.build_chunks_from_sections(sections, filename)
        name = str(item.get("name", item.get("display_name", item.get("business_name", ""))))

        for c in chunks:
            chunk_id = f"pms-{doc_type}-{batch_id}-{item_id}-{c.chunk_hash}"
            meta: dict[str, Any] = {
                "source": "pms",
                "type": doc_type,
                f"{doc_type}_id": item_id,
                "name": name,
                "import_batch": batch_id,
                "file_id": f"pms-{batch_id}",
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
    col.add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
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
