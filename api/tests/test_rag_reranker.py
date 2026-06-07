"""Unit tests for app.rag.reranker: rerank, Cohere, BGE fallback."""
from __future__ import annotations

from unittest.mock import MagicMock, patch



SAMPLE_DOCS = [
    {"chunk_hash": "a", "text": "Botox aftercare instructions."},
    {"chunk_hash": "b", "text": "Laser hair removal pricing."},
    {"chunk_hash": "c", "text": "Clinic opening hours."},
]


class TestRerank:
    def test_no_provider_returns_passthrough(self):
        with patch("app.rag.reranker.RERANKER_PROVIDER", ""):
            from app.rag.reranker import rerank
            result = rerank("test", SAMPLE_DOCS, top_k=2)
            assert len(result) == 2
            assert result[0]["chunk_hash"] == "a"

    def test_empty_docs_returns_empty(self):
        with patch("app.rag.reranker.RERANKER_PROVIDER", "cohere"):
            from app.rag.reranker import rerank
            assert rerank("test", []) == []

    def test_unknown_provider_passthrough(self):
        with patch("app.rag.reranker.RERANKER_PROVIDER", "unknown"):
            from app.rag.reranker import rerank
            result = rerank("test", SAMPLE_DOCS, top_k=2)
            assert len(result) == 2

    @patch("app.rag.reranker._rerank_cohere", return_value=[SAMPLE_DOCS[1], SAMPLE_DOCS[0]])
    def test_cohere_provider_dispatches(self, mock_cohere):
        with patch("app.rag.reranker.RERANKER_PROVIDER", "cohere"):
            from app.rag.reranker import rerank
            result = rerank("test", SAMPLE_DOCS, top_k=5)
            mock_cohere.assert_called_once()
            assert result[0]["chunk_hash"] == "b"

    @patch("app.rag.reranker._rerank_bge", return_value=[SAMPLE_DOCS[2], SAMPLE_DOCS[1]])
    def test_bge_provider_dispatches(self, mock_bge):
        with patch("app.rag.reranker.RERANKER_PROVIDER", "bge"):
            from app.rag.reranker import rerank
            result = rerank("test", SAMPLE_DOCS, top_k=5)
            mock_bge.assert_called_once()
            assert result[0]["chunk_hash"] == "c"

    def test_rerank_exception_falls_back_to_passthrough(self):
        with patch("app.rag.reranker.RERANKER_PROVIDER", "cohere"):
            with patch("app.rag.reranker._rerank_cohere", side_effect=Exception("API error")):
                from app.rag.reranker import rerank
                result = rerank("test", SAMPLE_DOCS, top_k=2)
                assert len(result) == 2
                assert result[0]["chunk_hash"] == "a"

    def test_top_k_larger_than_docs(self):
        with patch("app.rag.reranker.RERANKER_PROVIDER", ""):
            from app.rag.reranker import rerank
            result = rerank("test", SAMPLE_DOCS, top_k=100)
            assert len(result) == 3


class TestRerankCohere:
    def test_missing_cohere_falls_back_to_bge(self):
        with patch("app.rag.reranker.RERANKER_PROVIDER", "cohere"):
            with patch("app.rag.reranker._rerank_bge", return_value=SAMPLE_DOCS):
                from app.rag.reranker import rerank
                result = rerank("test", SAMPLE_DOCS, top_k=2)
                assert len(result) > 0

    def test_successful_cohere_call(self):
        mock_cohere_mod = MagicMock()
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.index = 1
        mock_result.relevance_score = 0.95
        mock_response = MagicMock()
        mock_response.results = [mock_result]
        mock_client.rerank.return_value = mock_response
        mock_cohere_mod.ClientV2.return_value = mock_client

        with patch.dict("sys.modules", {"cohere": mock_cohere_mod}):
            with patch("app.rag.reranker.RERANKER_PROVIDER", "cohere"):
                with patch("app.rag.reranker.RERANKER_API_KEY", "test-key"):
                    from app.rag.reranker import rerank
                    result = rerank("test", SAMPLE_DOCS, top_k=5)
                    assert len(result) == 1
                    assert result[0]["chunk_hash"] == "b"
                    assert result[0]["relevance_score"] == 0.95


class TestRerankBge:
    def test_missing_sentence_transformers_returns_passthrough(self):
        with patch("app.rag.reranker.RERANKER_PROVIDER", "bge"):
            with patch.dict("sys.modules", {"sentence_transformers": None}):
                from app.rag.reranker import rerank
                result = rerank("test", SAMPLE_DOCS, top_k=2)
                assert len(result) == 2

    def test_bge_called_with_correct_pairs(self):
        mock_st = MagicMock()
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.9, 0.1, 0.5]
        mock_st.CrossEncoder.return_value = mock_model

        with patch("app.rag.reranker.RERANKER_PROVIDER", "bge"):
            with patch.dict("sys.modules", {"sentence_transformers": mock_st}):
                from app.rag.reranker import rerank
                result = rerank("test", SAMPLE_DOCS, top_k=2)
                assert len(result) == 2
                assert result[0]["chunk_hash"] == "a"

    def test_bge_handles_zero_docs(self):
        mock_st = MagicMock()
        with patch("app.rag.reranker.RERANKER_PROVIDER", "bge"):
            with patch.dict("sys.modules", {"sentence_transformers": mock_st}):
                from app.rag.reranker import rerank
                result = rerank("test", [], top_k=5)
                assert result == []
