"""Unit tests for app.rag.citation_guard: validate, token overlap, metrics."""
from __future__ import annotations

from unittest.mock import patch


from app.rag.citation_guard import (
    _citation_found_in_context,
    _tokenize,
    get_rejection_rate,
    reset_metrics,
    validate,
)


SAMPLE_CHUNKS = [
    {"text": "Botox should not be performed during pregnancy or breastfeeding."},
    {"text": "Patients should avoid strenuous exercise for 24 hours after Botox."},
    {"text": "Results typically last 3-4 months depending on the individual."},
]


# ── _tokenize ───────────────────────────────────────────────────────────


class TestTokenize:
    def test_basic_text(self):
        tokens = _tokenize("Hello World!")
        assert tokens == ["hello", "world"]

    def test_empty_text(self):
        assert _tokenize("") == []

    def test_punctuation_removed(self):
        tokens = _tokenize("Botox: 24h post-op?")
        assert "botox" in tokens
        assert "24h" in tokens
        assert "post" in tokens
        assert "op" in tokens

    def test_lowercase(self):
        tokens = _tokenize("BOTOX AfterCare")
        assert tokens == ["botox", "aftercare"]

    def test_numbers_and_words(self):
        tokens = _tokenize("3-4 months")
        assert "3" in tokens
        assert "4" in tokens
        assert "months" in tokens


# ── _citation_found_in_context ──────────────────────────────────────────


class TestCitationFoundInContext:
    def test_exact_match_found(self):
        result = _citation_found_in_context(
            "Botox should not be performed during pregnancy",
            SAMPLE_CHUNKS,
        )
        assert result is True

    def test_partial_match_above_threshold(self):
        result = _citation_found_in_context(
            "avoid strenuous exercise for 24 hours after Botox",
            SAMPLE_CHUNKS,
        )
        assert result is True

    def test_no_match(self):
        result = _citation_found_in_context(
            "Laser hair removal is permanent after 6 sessions",
            SAMPLE_CHUNKS,
        )
        assert result is False

    def test_empty_citation_returns_true(self):
        result = _citation_found_in_context("", SAMPLE_CHUNKS)
        assert result is True

    def test_empty_context_chunks(self):
        result = _citation_found_in_context("Botox", [])
        assert result is False

    def test_citation_spans_multiple_chunks(self):
        result = _citation_found_in_context(
            "Patients should avoid strenuous exercise for 24 hours after",
            SAMPLE_CHUNKS,
        )
        assert result is True

    def test_single_word_citation(self):
        result = _citation_found_in_context("Botox", SAMPLE_CHUNKS)
        assert result is True

    def test_nonexistent_word(self):
        result = _citation_found_in_context("Xylophone", SAMPLE_CHUNKS)
        assert result is False


# ── validate ────────────────────────────────────────────────────────────


class TestValidate:
    def test_disabled_flag_passes(self):
        with patch("app.rag.citation_guard.CITATION_GUARD", False):
            passed, failures = validate("answer", ["citation"], SAMPLE_CHUNKS)
            assert passed is True
            assert failures == []

    def test_no_citations_passes(self):
        with patch("app.rag.citation_guard.CITATION_GUARD", True):
            passed, failures = validate("answer", [], SAMPLE_CHUNKS)
            assert passed is True
            assert failures == []

    def test_all_valid_citations(self):
        reset_metrics()
        with patch("app.rag.citation_guard.CITATION_GUARD", True):
            passed, failures = validate(
                "answer",
                ["Botox should not be performed during pregnancy"],
                SAMPLE_CHUNKS,
            )
            assert passed is True
            assert failures == []

    def test_some_invalid_citations(self):
        reset_metrics()
        with patch("app.rag.citation_guard.CITATION_GUARD", True):
            passed, failures = validate(
                "answer",
                ["Botox should not be performed during pregnancy", "Completely made up fact"],
                SAMPLE_CHUNKS,
            )
            # Soft block: passes if at least one citation is valid
            assert passed is True
            assert len(failures) == 1
            assert "Completely made up fact" in failures

    def test_all_invalid_citations(self):
        reset_metrics()
        with patch("app.rag.citation_guard.CITATION_GUARD", True):
            passed, failures = validate(
                "answer",
                ["Fake claim one", "Fake claim two"],
                SAMPLE_CHUNKS,
            )
            assert passed is False
            assert len(failures) == 2


# ── Metrics / Alert (T-2.5.3) ───────────────────────────────────────────


class TestRejectionRateAlert:
    def test_initial_rate_zero(self):
        reset_metrics()
        assert get_rejection_rate() == 0.0

    def test_rate_after_valid_citations(self):
        reset_metrics()
        with patch("app.rag.citation_guard.CITATION_GUARD", True):
            validate("a", ["Botox should not be performed during pregnancy"], SAMPLE_CHUNKS)
        assert get_rejection_rate() == 0.0

    def test_rate_after_rejections(self):
        reset_metrics()
        with patch("app.rag.citation_guard.CITATION_GUARD", True):
            validate("a", ["Botox should not be performed during pregnancy"], SAMPLE_CHUNKS)
            validate("a", ["fake claim"], SAMPLE_CHUNKS)
        rate = get_rejection_rate()
        assert rate == 0.5

    def test_rate_after_all_rejected(self):
        reset_metrics()
        with patch("app.rag.citation_guard.CITATION_GUARD", True):
            validate("a", ["fake one", "fake two"], SAMPLE_CHUNKS)
        assert get_rejection_rate() == 1.0

    def test_reset_metrics(self):
        reset_metrics()
        with patch("app.rag.citation_guard.CITATION_GUARD", True):
            validate("a", ["fake claim"], SAMPLE_CHUNKS)
        assert get_rejection_rate() > 0
        reset_metrics()
        assert get_rejection_rate() == 0.0
