"""RAG: chunking, embedding, Chroma storage, similarity search (Sprint 1).

Changes vs MVP:
- Uses app.chunking (token-aware, heading-aware, per-page PDF).
- Stores rich metadata per chunk: filename, section, page, char_start/end, chunk_hash.
- search() returns list[dict] with scores + metadata (not bare strings).
- Applies a cosine-distance threshold so the agent knows when KB is irrelevant.
- Idempotent: chunk IDs are deterministic (sha1 of file_id + chunk_hash) so
  re-indexing the same file overwrites instead of duplicating.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import chromadb
from openai import OpenAI

from . import chunking
from .config import get_settings, get_yaml_config

logger = logging.getLogger(__name__)

_settings = get_settings()
_rag_cfg = get_yaml_config().get("rag", {})
EMBED_MODEL = _rag_cfg.get("embedding_model", "text-embedding-3-small")
TOP_K = int(_rag_cfg.get("top_k", 15))
# cosine distance (1 - cos_sim). Empirically for text-embedding-3-small,
# distances below ~0.45 are usefully relevant; above ~0.60 is noise.
DISTANCE_THRESHOLD = float(_rag_cfg.get("distance_threshold", 0.85))

# Schema version — bump on any breaking change to collection layout.
EMBEDDING_VERSION = f"{EMBED_MODEL}:v1"


def _openai() -> OpenAI:
    return OpenAI(api_key=_settings.openai_api_key)


_chroma_client = None
_chroma_lock = threading.Lock()

def _chroma():
    global _chroma_client
    if _chroma_client is not None:
        return _chroma_client

    with _chroma_lock:
        if _chroma_client is not None:
            return _chroma_client

        if _settings.chroma_url:
            u = urlparse(_settings.chroma_url)
            _chroma_client = chromadb.HttpClient(host=u.hostname or "chroma", port=u.port or 8000)
        elif _settings.chroma_path:
            _chroma_client = chromadb.PersistentClient(path=_settings.chroma_path)
        else:
            raise RuntimeError("Neither CHROMA_URL nor CHROMA_PATH is configured")
        return _chroma_client


def _collection(tenant_id: UUID | str):
    name = f"tenant_{str(tenant_id).replace('-', '')}"
    return _chroma().get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine", "embedding_version": EMBEDDING_VERSION},
    )


def _count_all_chunks(tenant_id: UUID | str) -> int:
    """Count total chunks in collection for debugging."""
    try:
        col = _collection(tenant_id)
        return col.count()
    except Exception:
        return 0


def embed_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    resp = _openai().embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]


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


def delete_file(tenant_id: UUID | str, file_id: UUID | str) -> None:
    try:
        col = _collection(tenant_id)
        fid = str(file_id)
        total_before = col.count()

        # Direct where-based delete — simpler and more reliable
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
) -> list[dict[str, Any]]:
    """Return top-k relevant chunks from Chroma vector store.
    Each result is a dict with text, score, distance, and metadata.
    """
    thr = DISTANCE_THRESHOLD if threshold is None else threshold

    try:
        col = _collection(tenant_id)
        cnt = col.count()
        logger.info("search: tenant=%s collection_count=%d query='%s'", tenant_id, cnt, query[:80])
        if cnt == 0:
            logger.info("search: collection is empty, returning []")
            return []
        q_emb = embed_batch([query])[0]
        res = col.query(
            query_embeddings=[q_emb],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
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


def _all_chunks(tenant_id: UUID | str) -> tuple[list[str], list[dict]]:
    """Fetch all chunk IDs + metadatas from a tenant collection."""
    col = _collection(tenant_id)
    cnt = col.count()
    if cnt == 0:
        return [], []
    r = col.get(include=["metadatas"])
    ids: list[str] = r.get("ids", [])
    metas: list[dict] = r.get("metadatas", []) or []
    return ids, metas


def deduplicate_collection(tenant_id: UUID | str) -> dict:
    """Remove duplicate chunks (same filename + chunk_hash) from Chroma,
    keeping only one copy. Returns stats."""
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
        col.delete(ids=to_delete)
        logger.info("dedup: removed %d duplicate chunks, %d unique remain",
                     len(to_delete), len(by_key))
    else:
        logger.info("dedup: no duplicates found (%d chunks)", len(ids))
    return {"total": len(ids), "removed": len(to_delete)}


def purge_orphans(tenant_id: UUID | str, active_file_ids: set[str]) -> dict:
    """Remove Chroma chunks whose file_id is not in active_file_ids
    (i.e. chunks left behind by old uploads / failed deletes). Returns stats."""
    col = _collection(tenant_id)
    ids, metas = _all_chunks(tenant_id)
    if not ids:
        return {"total": 0, "removed": 0}

    to_delete: list[str] = []
    for cid, meta in zip(ids, metas):
        fid = meta.get("file_id") or ""
        if fid not in active_file_ids:
            to_delete.append(cid)

    if to_delete:
        col.delete(ids=to_delete)
        logger.info("purge: removed %d orphan chunks (active=%d, total=%d)",
                     len(to_delete), len(active_file_ids), len(ids))
    else:
        logger.info("purge: no orphans found (%d chunks)", len(ids))
    return {"total": len(ids), "removed": len(to_delete)}
