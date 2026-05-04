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

from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

import chromadb
from openai import OpenAI

from . import chunking
from .config import get_settings, get_yaml_config

_settings = get_settings()
_rag_cfg = get_yaml_config().get("rag", {})
EMBED_MODEL = _rag_cfg.get("embedding_model", "text-embedding-3-small")
TOP_K = int(_rag_cfg.get("top_k", 5))
# cosine distance (1 - cos_sim). Empirically for text-embedding-3-small,
# distances below ~0.45 are usefully relevant; above ~0.60 is noise.
DISTANCE_THRESHOLD = float(_rag_cfg.get("distance_threshold", 0.60))

# Schema version — bump on any breaking change to collection layout.
EMBEDDING_VERSION = f"{EMBED_MODEL}:v1"


def _openai() -> OpenAI:
    return OpenAI(api_key=_settings.openai_api_key)


_chroma_client = None

def _chroma():
    global _chroma_client
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
    # Deterministic IDs: re-indexing the same content is a no-op (upsert).
    ids = [f"{file_id}-{i}-{c.chunk_hash}" for i, c in enumerate(chunks)]
    texts = [c.text for c in chunks]
    metadatas = [c.to_metadata(str(file_id)) for c in chunks]
    # Drop anything already stored for this file_id before re-adding, so
    # chunks that disappeared after re-upload don't linger.
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
        col.delete(where={"file_id": str(file_id)})
    except Exception as e:
        print(f"[rag] delete failed: {e}", flush=True)


_QUERY_SYNONYMS = {
    "price": ["pricing", "plans", "cost", "subscription", "plans and pricing", "how much"],
    "return": ["refund", "returns", "exchange", "money back", "return policy"],
    "shipping": ["delivery", "ship", "dispatch", "tracking", "shipping policy"],
    "cancel": ["cancellation", "cancel subscription", "stop", "unsubscribe"],
    "contact": ["support", "help", "email", "phone", "reach out", "talk to"],
    "discount": ["coupon", "promo", "sale", "offer", "deal", "promotion"],
    "account": ["login", "sign in", "register", "profile", "settings"],
    "payment": ["pay", "billing", "invoice", "card", "credit"],
}

_SEARCH_SYNONYMS = {
    "what is the price": "pricing plans cost subscription",
    "how to make a return": "return refund exchange policy",
    "how much": "pricing plans cost",
    "return policy": "return refund exchange money back",
}

def search(
    tenant_id: UUID | str,
    query: str,
    top_k: int = TOP_K,
    threshold: float | None = None,
) -> list[dict[str, Any]]:
    """Return top-k relevant chunks. Each result is a dict:
        {id, text, score, distance, file_id, filename, section, page,
         char_start, char_end, chunk_hash}
    Chunks farther than `threshold` cosine distance are dropped.
    Uses query expansion as fallback when initial results are empty or all
    above threshold — short user queries like "what is the price" may not
    embed closely to document text.
    """
    thr = DISTANCE_THRESHOLD if threshold is None else threshold

    def _raw(q):
        try:
            col = _collection(tenant_id)
            if col.count() == 0:
                return []
            q_emb = embed_batch([q])[0]
            res = col.query(
                query_embeddings=[q_emb],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )
            docs = (res.get("documents") or [[]])[0]
            metas = (res.get("metadatas") or [[]])[0]
            dists = (res.get("distances") or [[]])[0]
            ids = (res.get("ids") or [[]])[0]
            out: list[dict[str, Any]] = []
            for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists)):
                if dist is None or dist > thr:
                    continue
                meta = meta or {}
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
                        "chunk_hash": meta.get("chunk_hash", ""),
                    }
                )
            return out
        except Exception as e:
            print(f"[rag] search failed: {e}", flush=True)
            return []

    # Try exact query first
    out = _raw(query)
    if out:
        return out

    # Try synonym expansions
    q_lower = query.lower().strip()
    candidates = []
    # 1. Check full-query synonyms
    if q_lower in _SEARCH_SYNONYMS:
        candidates.append(_SEARCH_SYNONYMS[q_lower])
    # 2. Check keyword-based synonyms
    for keyword, synonyms in _QUERY_SYNONYMS.items():
        if keyword in q_lower:
            candidates.extend(synonyms)
    # 3. Try each candidate
    for candidate in candidates:
        print(f"[rag] expanding query '{query}' -> '{candidate}'", flush=True)
        out = _raw(candidate)
        if out:
            print(f"[rag] found {len(out)} results with '{candidate}'", flush=True)
            return out

    return []
