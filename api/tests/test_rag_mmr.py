"""Unit tests for app.rag.mmr: mmr_diversify, cosine sim, select_one."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.rag.mmr import _cosine_sim, _mmr_select_one


SIMPLE_EMBEDDINGS = [
    [1.0, 0.0, 0.0],
    [0.0, 1.0, 0.0],
    [0.0, 0.0, 1.0],
    [0.5, 0.5, 0.0],
]

SAMPLE_RESULTS = [
    {"chunk_hash": "a", "text": "A"},
    {"chunk_hash": "b", "text": "B"},
    {"chunk_hash": "c", "text": "C"},
    {"chunk_hash": "d", "text": "D"},
]


# ── _cosine_sim ─────────────────────────────────────────────────────────


class TestCosineSim:
    def test_identical_vectors(self):
        assert _cosine_sim([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert _cosine_sim([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_zero_vector(self):
        assert _cosine_sim([0.0, 0.0], [1.0, 0.0]) == pytest.approx(0.0)
        assert _cosine_sim([1.0, 0.0], [0.0, 0.0]) == pytest.approx(0.0)

    def test_partial_similarity(self):
        sim = _cosine_sim([1.0, 0.0], [0.5, 0.5])
        expected = (0.5) / ((1.0) ** 0.5 * (0.25 + 0.25) ** 0.5)
        assert sim == pytest.approx(expected)

    def test_negative_values(self):
        sim = _cosine_sim([1.0, 0.0], [-1.0, 0.0])
        assert sim == pytest.approx(-1.0)


# ── _mmr_select_one ─────────────────────────────────────────────────────


class TestMmrSelectOne:
    def test_no_selected_returns_most_relevant(self):
        candidates = [0, 1, 2]
        sim_to_query = [0.9, 0.5, 0.3]
        best = _mmr_select_one(candidates, [], sim_to_query, SIMPLE_EMBEDDINGS, 0.5)
        assert best == 0

    def test_with_selected_diversifies(self):
        sim_to_query = [0.9, 0.3, 0.2]
        selected = [0]
        best = _mmr_select_one([1, 2], selected, sim_to_query, SIMPLE_EMBEDDINGS, 0.3)
        assert best in (1, 2)

    def test_high_lambda_ignores_diversity(self):
        sim_to_query = [0.9, 0.8, 0.3]
        selected = [0]
        best = _mmr_select_one([1, 2], selected, sim_to_query, SIMPLE_EMBEDDINGS, 0.9)
        assert best == 1  # relevance dominates


# ── mmr_diversify ───────────────────────────────────────────────────────


class TestMmrDiversify:
    def test_lambda_zero_returns_passthrough(self):
        from app.rag.mmr import mmr_diversify
        result = mmr_diversify(SAMPLE_RESULTS, "query", lambda_=0.0, top_k=5)
        assert result == SAMPLE_RESULTS

    def test_empty_results(self):
        from app.rag.mmr import mmr_diversify
        assert mmr_diversify([], "query", lambda_=0.5, top_k=5) == []

    def test_fewer_results_than_top_k(self):
        from app.rag.mmr import mmr_diversify
        result = mmr_diversify(SAMPLE_RESULTS[:2], "query", lambda_=0.5, top_k=5)
        assert len(result) == 2
        assert result == SAMPLE_RESULTS[:2]

    @patch("app.rag.mmr.embed_batch", return_value=SIMPLE_EMBEDDINGS)
    def test_successful_mmr(self, mock_embed):
        from app.rag.mmr import mmr_diversify
        result = mmr_diversify(SAMPLE_RESULTS, "diversity query", lambda_=0.5, top_k=2)
        assert len(result) == 2
        mock_embed.assert_called_once()

    @patch("app.rag.mmr.embed_batch", side_effect=Exception("API error"))
    def test_embedding_failure_fallback(self, mock_embed):
        from app.rag.mmr import mmr_diversify
        result = mmr_diversify(SAMPLE_RESULTS, "query", lambda_=0.5, top_k=2)
        assert len(result) == 2

    @patch("app.rag.mmr.embed_batch", return_value=[[]])
    def test_empty_embedding_fallback(self, mock_embed):
        from app.rag.mmr import mmr_diversify
        result = mmr_diversify(SAMPLE_RESULTS, "query", lambda_=0.5, top_k=2)
        assert len(result) == 2

    @patch("app.rag.mmr.embed_batch", return_value=SIMPLE_EMBEDDINGS)
    def test_preserves_diversity_low_lambda(self, mock_embed):
        from app.rag.mmr import mmr_diversify
        result = mmr_diversify(SAMPLE_RESULTS, "query", lambda_=0.1, top_k=2)
        assert len(result) == 2
