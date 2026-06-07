"""Unit tests for app.rag.translation: translate_and_search, RRF merge, ASCII detection."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.rag.translation import _is_mostly_ascii, _rrf_merge


# ── _is_mostly_ascii ────────────────────────────────────────────────────


class TestIsMostlyAscii:
    def test_empty_string(self):
        assert _is_mostly_ascii("") is True

    def test_pure_ascii(self):
        assert _is_mostly_ascii("Hello world") is True

    def test_mostly_ascii(self):
        text = "Café"  # 3 ASCII + 1 non-ASCII = 75% → False (needs >90%)
        assert _is_mostly_ascii(text) is False

    def test_above_threshold(self):
        text = "abcdefghijklm" + "ñ"  # 13 ASCII + 1 non-ASCII = 92.8% → True
        assert _is_mostly_ascii(text) is True

    def test_pure_non_ascii(self):
        assert _is_mostly_ascii("übercool") is False  # 6/8 = 75% < 90%
        assert _is_mostly_ascii("Привет") is False

    def test_mixed_languages(self):
        assert _is_mostly_ascii("Guten Tag") is True
        assert _is_mostly_ascii("¿Como estas?") is True  # all ASCII


# ── _rrf_merge ──────────────────────────────────────────────────────────


class TestRrfMerge:
    def test_single_list(self):
        docs = [{"chunk_hash": "a", "text": "A"}, {"chunk_hash": "b", "text": "B"}]
        result = _rrf_merge(docs)
        assert len(result) == 2
        assert result[0]["chunk_hash"] == "a"

    def test_two_lists_merged(self):
        list1 = [{"chunk_hash": "a", "text": "A"}, {"chunk_hash": "b", "text": "B"}]
        list2 = [{"chunk_hash": "c", "text": "C"}, {"chunk_hash": "d", "text": "D"}]
        result = _rrf_merge(list1, list2)
        assert len(result) == 4

    def test_dedup_by_chunk_hash(self):
        list1 = [{"chunk_hash": "a", "text": "A"}, {"chunk_hash": "b", "text": "B"}]
        list2 = [{"chunk_hash": "a", "text": "A from other"}]
        result = _rrf_merge(list1, list2)
        assert len(result) == 2

    def test_with_weights(self):
        list1 = [{"chunk_hash": "a", "text": "A"}, {"chunk_hash": "b", "text": "B"}]
        list2 = [{"chunk_hash": "a", "text": "A"}, {"chunk_hash": "c", "text": "C"}]
        result = _rrf_merge(list1, list2, weights=[2.0, 1.0])
        assert len(result) == 3

    def test_empty_list(self):
        assert _rrf_merge([]) == []

    def test_fallback_key_when_no_chunk_hash(self):
        docs = [{"id": "x", "text": "X"}, {"id": "y", "text": "Y"}]
        result = _rrf_merge(docs)
        assert len(result) == 2

    def test_reverse_ranking(self):
        list1 = [{"chunk_hash": "a", "text": "A"}, {"chunk_hash": "b", "text": "B"}]
        list2 = [{"chunk_hash": "b", "text": "B"}, {"chunk_hash": "a", "text": "A"}]
        result = _rrf_merge(list1, list2)
        assert len(result) == 2


# ── translate_and_search ────────────────────────────────────────────────


class TestTranslateAndSearch:
    @patch("app.rag.translation.QUERY_TRANSLATION", False)
    @patch("app.rag.translation.rag_search", return_value=[{"chunk_hash": "a"}])
    @pytest.mark.asyncio
    async def test_disabled_flag_returns_single_search(self, mock_search):
        from app.rag.translation import translate_and_search
        result = await translate_and_search("t1", "hello", 10, 0.8)
        mock_search.assert_called_once_with("t1", "hello", 10, 0.8, None)
        assert result == [{"chunk_hash": "a"}]

    @patch("app.rag.translation.QUERY_TRANSLATION", True)
    @patch("app.rag.translation.rag_search", return_value=[{"chunk_hash": "a"}])
    @patch("app.rag.translation.translate_query", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_english_query_skips_translate(self, mock_translate, mock_search):
        from app.rag.translation import translate_and_search
        result = await translate_and_search("t1", "Hello world", 10, 0.8)
        mock_search.assert_called_once()
        mock_translate.assert_not_called()
        assert result == [{"chunk_hash": "a"}]

    @patch("app.rag.translation.QUERY_TRANSLATION", True)
    @patch("app.rag.translation.rag_search", return_value=[{"chunk_hash": "a"}])
    @patch("app.rag.translation.translate_query", new_callable=AsyncMock, return_value="Hello world")
    @pytest.mark.asyncio
    async def test_non_english_does_dual_search(self, mock_translate, mock_search):
        from app.rag.translation import translate_and_search
        await translate_and_search("t1", "Médecine", 10, 0.8)
        assert mock_translate.call_count == 1
        assert mock_search.call_count == 2

    @patch("app.rag.translation.QUERY_TRANSLATION", True)
    @patch("app.rag.translation.rag_search", return_value=[{"chunk_hash": "a"}])
    @patch("app.rag.translation.translate_query", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_translate_returns_same_as_original(self, mock_translate, mock_search):
        from app.rag.translation import translate_and_search
        mock_translate.return_value = "Médecine"
        mock_search.return_value = [{"chunk_hash": "a"}]
        result = await translate_and_search(
            "t1", "Médecine", 10, 0.8, {"source": "kb"}
        )
        assert mock_search.call_count == 1
        mock_search.assert_called_with("t1", "Médecine", 10, 0.8, {"source": "kb"})
        assert result == [{"chunk_hash": "a"}]

    @patch("app.rag.translation.QUERY_TRANSLATION", True)
    @patch("app.rag.translation.rag_search", return_value=[{"chunk_hash": "a"}])
    @patch("app.rag.translation.translate_query", new_callable=AsyncMock, return_value="")
    @pytest.mark.asyncio
    async def test_empty_translate_fallback_to_single(self, mock_translate, mock_search):
        from app.rag.translation import translate_and_search
        result = await translate_and_search("t1", "Médecine", 10, 0.8)
        mock_search.assert_called_once()
        mock_translate.assert_called_once()
        assert result == [{"chunk_hash": "a"}]
