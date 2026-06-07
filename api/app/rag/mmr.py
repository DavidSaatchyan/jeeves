"""MMR (Maximum Marginal Relevance) diversification."""
from __future__ import annotations

import math
from typing import Any

from .client import embed_batch


def mmr_diversify(
    results: list[dict[str, Any]],
    query: str,
    lambda_: float = 0.5,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    if lambda_ <= 0.0 or not results:
        return results[:top_k]

    if len(results) <= top_k:
        return results

    texts = [r.get("text", "") for r in results]
    try:
        embeddings = embed_batch(texts)
    except Exception:
        return results[:top_k]

    query_emb = embeddings[0] if embeddings else []

    selected: list[int] = []
    candidate_indices = list(range(len(results)))

    if not query_emb:
        return results[:top_k]

    sim_to_query = [_cosine_sim(query_emb, e) for e in embeddings]

    while len(selected) < top_k and candidate_indices:
        best_idx = _mmr_select_one(
            candidate_indices, selected, sim_to_query, embeddings, lambda_
        )
        selected.append(best_idx)
        candidate_indices.remove(best_idx)

    return [dict(results[i]) for i in selected]


def _mmr_select_one(
    candidates: list[int],
    selected: list[int],
    sim_to_query: list[float],
    embeddings: list[list[float]],
    lambda_: float,
) -> int:
    best_score = -float("inf")
    best_idx = candidates[0]
    for idx in candidates:
        relevance = sim_to_query[idx]
        if selected:
            max_sim = max(_cosine_sim(embeddings[idx], embeddings[s]) for s in selected)
        else:
            max_sim = 0.0
        mmr = lambda_ * relevance - (1 - lambda_) * max_sim
        if mmr > best_score:
            best_score = mmr
            best_idx = idx
    return best_idx


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
