from __future__ import annotations

import hashlib
import logging
from typing import Any
from uuid import UUID

from .client import _collection, embed_batch

logger = logging.getLogger(__name__)


def _textualize_service(svc: dict[str, Any]) -> str:
    parts = [f"Service: {svc.get('name', '')}"]
    price = svc.get("price")
    if price is not None:
        dollars = float(price) / 100 if isinstance(price, int) else float(price)
        parts.append(f"Price: ${dollars:.2f}")
    duration = svc.get("duration_in_minutes")
    if duration is not None:
        parts.append(f"Duration: {int(duration)} minutes")
    category = svc.get("category", "")
    if category:
        parts.append(f"Category: {category}")
    description = svc.get("description", "")
    if description:
        parts.append(f"Description: {description}")
    telehealth = svc.get("telehealth_enabled")
    if telehealth is not None:
        parts.append(f"Telehealth: {'Yes' if telehealth else 'No'}")
    online = svc.get("online_booking_enabled", svc.get("online_bookable"))
    if online is not None:
        parts.append(f"Online booking: {'Yes' if online else 'No'}")
    item_code = svc.get("item_code", "")
    if item_code:
        parts.append(f"Code: {item_code}")
    return "\n".join(parts)


def _textualize_practitioner(prac: dict[str, Any]) -> str:
    parts = [f"Practitioner: {prac.get('display_name', prac.get('first_name', ''))}"]
    title = prac.get("title", "")
    if title:
        parts.append(f"Title: {title}")
    designation = prac.get("designation", "")
    if designation:
        parts.append(f"Specialty: {designation}")
    description = prac.get("description", "")
    if description:
        parts.append(f"Description: {description}")
    active = prac.get("active", True)
    parts.append(f"Accepting new patients: {'Yes' if active else 'No'}")
    return "\n".join(parts)


def _textualize_clinic(clinic: dict[str, Any]) -> str:
    parts = [f"Clinic: {clinic.get('business_name', clinic.get('name', ''))}"]
    address = ", ".join(filter(None, [
        clinic.get("address", ""),
        clinic.get("city", ""),
        clinic.get("state", ""),
        clinic.get("postcode", ""),
        clinic.get("country", ""),
    ]))
    if address:
        parts.append(f"Address: {address}")
    phone = clinic.get("phone", "")
    if phone:
        parts.append(f"Phone: {phone}")
    email = clinic.get("email", "")
    if email:
        parts.append(f"Email: {email}")
    website = clinic.get("website", "")
    if website:
        parts.append(f"Website: {website}")
    timezone = clinic.get("timezone", "")
    if timezone:
        parts.append(f"Timezone: {timezone}")
    additional = clinic.get("additional_info", "")
    if additional:
        parts.append(f"Additional info: {additional}")
    return "\n".join(parts)


def _delete_by_type_and_batch(
    tenant_id: UUID | str,
    doc_type: str,
    batch_id: str,
) -> int:
    col = _collection(tenant_id)
    try:
        before = col.count()
        col.delete(where={"$and": [{"type": doc_type}, {"import_batch": batch_id}]})
        after = col.count()
        removed = before - after
        if removed:
            logger.info("crm_indexer: deleted %d %s docs (batch=%s)", removed, doc_type, batch_id)
        return removed
    except Exception as e:
        logger.warning("crm_indexer: delete error for %s batch=%s: %s", doc_type, batch_id, e)
        return 0


def _index_type(
    tenant_id: UUID | str,
    items: list[dict[str, Any]],
    batch_id: str,
    doc_type: str,
    textualize_fn: Any,
    id_field: str = "id",
    extra_meta: dict[str, Any] | None = None,
) -> int:
    if not items:
        return 0

    _delete_by_type_and_batch(tenant_id, doc_type, batch_id)

    texts: list[str] = []
    metadatas: list[dict] = []
    ids: list[str] = []

    for i, item in enumerate(items):
        text = textualize_fn(item) if callable(textualize_fn) else str(item)
        item_id = str(item.get(id_field, "") or f"unknown-{i}")
        chunk_id = f"{doc_type}-{batch_id}-{item_id}"
        meta: dict[str, Any] = {
            "type": doc_type,
            f"{doc_type}_id": item_id,
            "name": str(item.get("name", item.get("display_name", item.get("business_name", "")))),
            "import_batch": batch_id,
            "file_id": f"crm-{batch_id}",
            "filename": f"crm-{doc_type}-{batch_id}.txt",
            "section": doc_type.capitalize(),
            "chunk_hash": hashlib.sha1(text.encode("utf-8")).hexdigest()[:16],
            "char_start": 0,
            "char_end": len(text),
        }
        if doc_type == "service":
            price = item.get("price")
            meta["price"] = str(price) if price is not None else ""
            meta["category"] = str(item.get("category", ""))
        elif doc_type == "practitioner":
            meta["designation"] = str(item.get("designation", ""))
            meta["active"] = bool(item.get("active", True))
        if extra_meta:
            meta.update(extra_meta)
        texts.append(text)
        metadatas.append(meta)
        ids.append(chunk_id)

    embeddings = embed_batch(texts)
    col = _collection(tenant_id)
    col.add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
    logger.info("crm_indexer: indexed %d %s docs (batch=%s)", len(items), doc_type, batch_id)
    return len(items)


def index_services(
    tenant_id: UUID | str,
    services: list[dict[str, Any]],
    batch_id: str,
) -> int:
    return _index_type(tenant_id, services, batch_id, "service", _textualize_service)


def index_practitioners(
    tenant_id: UUID | str,
    practitioners: list[dict[str, Any]],
    batch_id: str,
) -> int:
    return _index_type(tenant_id, practitioners, batch_id, "practitioner", _textualize_practitioner)


def index_clinic(
    tenant_id: UUID | str,
    clinic: dict[str, Any] | None,
    batch_id: str,
) -> int:
    items = [clinic] if clinic else []
    return _index_type(tenant_id, items, batch_id, "clinic", _textualize_clinic)


def delete_by_type_and_batch(
    tenant_id: UUID | str,
    doc_type: str,
    batch_id: str,
) -> int:
    return _delete_by_type_and_batch(tenant_id, doc_type, batch_id)
