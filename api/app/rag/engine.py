from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from .. import chunking
from .client import _collection, embed_batch
from .config import DISTANCE_THRESHOLD, TOP_K

logger = logging.getLogger(__name__)


def _count_all_chunks(tenant_id: UUID | str) -> int:
    try:
        col = _collection(tenant_id)
        return col.count()
    except Exception:
        return 0


def index_file(tenant_id: UUID | str, file_id: UUID | str, path: Path) -> int:
    chunks = chunking.build_chunks(path)
    if not chunks:
        return 0
    col = _collection(tenant_id)
    ids = [f"{file_id}-{i}-{c.chunk_hash}" for i, c in enumerate(chunks)]
    texts = [c.text for c in chunks]
    metadatas = [c.to_metadata(str(file_id)) for c in chunks]
    try:
        col.delete(where={"file_id": str(file_id)})
    except Exception:
        pass
    embeddings = embed_batch(texts)
    col.add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
    return len(chunks)


def delete_file(tenant_id: UUID | str, file_id: UUID | str):
    try:
        col = _collection(tenant_id)
        fid = str(file_id)
        total_before = col.count()
        col.delete(where={"file_id": fid})
        total_after = col.count()
        logger.info("delete: %s %d -> %d chunks", col.name, total_before, total_after)
    except Exception as e:
        logger.error("delete failed: %s", e)


def search(
    tenant_id: UUID | str,
    query: str,
    top_k: int = TOP_K,
    threshold: float | None = None,
    where: dict | None = None,
) -> list[dict[str, Any]]:
    thr = DISTANCE_THRESHOLD if threshold is None else threshold

    try:
        col = _collection(tenant_id)
        cnt = col.count()
        logger.info("search: tenant=%s collection_count=%d query='%s' where=%s", tenant_id, cnt, query[:80], where)
        if cnt == 0:
            logger.info("search: collection is empty, returning []")
            return []
        q_emb = embed_batch([query])[0]
        query_kwargs = dict(
            query_embeddings=[q_emb],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        if where:
            query_kwargs["where"] = where
        res = col.query(**query_kwargs)
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        ids = (res.get("ids") or [[]])[0]
        raw_log = []
        for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists)):
            fname = (meta or {}).get("filename", "?")
            raw_log.append(f"  [{i}] dist={dist:.4f} file={fname} text={doc[:80]}")
        logger.debug("search raw results (%d):\n%s", len(docs), "\n".join(raw_log))
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists)):
            meta = meta or {}
            h = meta.get("chunk_hash", "") or ""
            if h and h in seen:
                continue
            if h:
                seen.add(h)
            out.append(
                {
                    "id": ids[i] if i < len(ids) else f"unknown-{i}",
                    "text": doc,
                    "distance": float(dist),
                    "score": round(1.0 - float(dist), 4),
                    "file_id": meta.get("file_id"),
                    "filename": meta.get("filename", ""),
                    "section": meta.get("section", ""),
                    "page": meta.get("page"),
                    "char_start": meta.get("char_start"),
                    "char_end": meta.get("char_end"),
                    "chunk_hash": h,
                }
            )
        if out and out[0]["distance"] > thr:
            logger.info("search: best dist=%.4f > %.2f, treating as empty", out[0]["distance"], thr)
            return []
        logger.info(
            "search passed threshold(%f): %d/%d results\n%s",
            thr, len(out), len(docs),
            "\n".join(f"  [{i}] dist={r['distance']:.4f} score={r['score']:.4f} "
                      f"file={r['filename']} sect={r['section'][:40]} "
                      f"text={r['text'][:120]!r}"
                      for i, r in enumerate(out))
        )
        return out
    except Exception as e:
        logger.error("search failed: %s", e)
        return []
