"""Query translation — dual search EN + original with RRF merge."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..core.ai.generator import translate_query
from .config import QUERY_TRANSLATION
from .engine import search as rag_search

logger = logging.getLogger(__name__)


async def translate_and_search(
    tenant_id: str,
    query: str,
    top_k: int,
    threshold: float,
    where: dict | None = None,
) -> list[dict[str, Any]]:
    if not QUERY_TRANSLATION:
        return await asyncio.to_thread(rag_search, tenant_id, query, top_k, threshold, where)

    is_english = _is_mostly_ascii(query)
    if is_english:
        return await asyncio.to_thread(rag_search, tenant_id, query, top_k, threshold, where)

    translated = await translate_query(query)
    if translated == query or not translated:
        return await asyncio.to_thread(rag_search, tenant_id, query, top_k, threshold, where)

    original_fut = asyncio.to_thread(rag_search, tenant_id, query, top_k, threshold, where)
    translated_fut = asyncio.to_thread(rag_search, tenant_id, translated, top_k, threshold, where)
    original_results, translated_results = await asyncio.gather(original_fut, translated_fut)

    return _rrf_merge(original_results, translated_results, weights=[1.0, 1.2])


def _is_mostly_ascii(text: str) -> bool:
    if not text:
        return True
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    return ascii_chars / len(text) > 0.9


def _rrf_merge(
    *lists: list[dict[str, Any]],
    weights: list[float] | None = None,
    k: int = 60,
) -> list[dict[str, Any]]:
    scores: dict[str, float] = {}
    items: dict[str, dict[str, Any]] = {}
    w = weights or [1.0] * len(lists)
    for rank_list, weight in zip(lists, w):
        for i, item in enumerate(rank_list):
            key = item.get("chunk_hash", item.get("id", str(i)))
            scores[key] = scores.get(key, 0.0) + weight / (k + i + 1)
            items[key] = item
    return sorted(items.values(), key=lambda x: scores.get(x.get("chunk_hash", ""), 0), reverse=True)
