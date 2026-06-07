"""Reranker — Cohere Rerank 3.5 with local BGE fallback."""
from __future__ import annotations

import logging
from typing import Any

from .config import RERANKER_API_KEY, RERANKER_MODEL, RERANKER_PROVIDER

logger = logging.getLogger(__name__)


def rerank(
    query: str,
    docs: list[dict[str, Any]],
    top_k: int = 10,
) -> list[dict[str, Any]]:
    if not RERANKER_PROVIDER:
        return docs[:top_k]

    if not docs:
        return []

    texts = [d.get("text", "") for d in docs]

    try:
        if RERANKER_PROVIDER == "cohere":
            return _rerank_cohere(query, texts, docs, top_k)
        elif RERANKER_PROVIDER == "bge":
            return _rerank_bge(query, texts, docs, top_k)
        else:
            logger.warning("Unknown reranker provider: %s", RERANKER_PROVIDER)
            return docs[:top_k]
    except Exception as e:
        logger.error("Reranker failed: %s", e)
        return docs[:top_k]


def _rerank_cohere(
    query: str,
    texts: list[str],
    docs: list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    try:
        import cohere
    except ImportError:
        logger.warning("cohere SDK not installed, falling back to BGE")
        return _rerank_bge(query, texts, docs, top_k)

    client = cohere.ClientV2(api_key=RERANKER_API_KEY)
    response = client.rerank(
        model=RERANKER_MODEL,
        query=query,
        documents=texts,
        top_n=top_k,
    )

    ranked: list[dict[str, Any]] = []
    for result in response.results:
        idx = result.index
        ranked.append(dict(docs[idx]))
        ranked[-1]["relevance_score"] = result.relevance_score
    ranked.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    return ranked


def _rerank_bge(
    query: str,
    texts: list[str],
    docs: list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    try:
        from sentence_transformers import CrossEncoder
    except ImportError:
        logger.warning("sentence-transformers not installed, returning unranked docs")
        return docs[:top_k]

    model = CrossEncoder(RERANKER_MODEL)
    pairs = [[query, t] for t in texts]
    scores = model.predict(pairs)

    scored = list(zip(scores, docs))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [dict(d) for _, d in scored[:top_k]]
