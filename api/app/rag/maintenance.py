from __future__ import annotations

import logging
from uuid import UUID

from .batch import batch_delete_ids
from .client import _collection

logger = logging.getLogger(__name__)


def _all_chunks(tenant_id: UUID | str) -> tuple[list[str], list[dict]]:
    col = _collection(tenant_id)
    cnt = col.count()
    if cnt == 0:
        return [], []
    r = col.get(include=["metadatas"])
    ids: list[str] = r.get("ids", [])
    metas: list[dict] = r.get("metadatas", []) or []
    return ids, metas


def deduplicate_collection(tenant_id: UUID | str) -> dict:
    col = _collection(tenant_id)
    ids, metas = _all_chunks(tenant_id)
    if not ids:
        return {"total": 0, "removed": 0}

    by_key: dict[str, list[str]] = {}
    for cid, meta in zip(ids, metas):
        key = f"{meta.get('filename', '?')}:{meta.get('chunk_hash', '')}"
        by_key.setdefault(key, []).append(cid)

    to_delete: list[str] = []
    for key, cids in by_key.items():
        for cid in cids[1:]:
            to_delete.append(cid)

    if to_delete:
        batch_delete_ids(col, to_delete)
        logger.info("dedup: removed %d duplicate chunks, %d unique remain",
                     len(to_delete), len(by_key))
    else:
        logger.info("dedup: no duplicates found (%d chunks)", len(ids))
    return {"total": len(ids), "removed": len(to_delete)}


def purge_orphans(tenant_id: UUID | str, active_file_ids: set[str]) -> dict:
    col = _collection(tenant_id)
    ids, metas = _all_chunks(tenant_id)
    if not ids:
        return {"total": 0, "removed": 0}

    to_delete: list[str] = []
    for cid, meta in zip(ids, metas):
        if meta.get("source") == "pms":
            continue  # PMS chunks are managed by the sync — never purge
        fid = meta.get("file_id") or ""
        if fid not in active_file_ids:
            to_delete.append(cid)

    if to_delete:
        batch_delete_ids(col, to_delete)
        logger.info("purge: removed %d orphan chunks (active=%d, total=%d)",
                     len(to_delete), len(active_file_ids), len(ids))
    else:
        logger.info("purge: no orphans found (%d chunks)", len(ids))
    return {"total": len(ids), "removed": len(to_delete)}
