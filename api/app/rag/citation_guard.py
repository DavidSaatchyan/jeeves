"""Programmatic citation validation via token overlap."""
from __future__ import annotations

import logging
import threading
from typing import Any

from .config import CITATION_GUARD

logger = logging.getLogger(__name__)

_TOKEN_OVERLAP_THRESHOLD = 0.5
_REJECT_RATE_ALERT_THRESHOLD = 0.2

_total_citations_checked = 0
_total_citations_rejected = 0
_metrics_lock = threading.Lock()


def get_rejection_rate() -> float:
    with _metrics_lock:
        if _total_citations_checked == 0:
            return 0.0
        return _total_citations_rejected / _total_citations_checked


def reset_metrics() -> None:
    global _total_citations_checked, _total_citations_rejected
    with _metrics_lock:
        _total_citations_checked = 0
        _total_citations_rejected = 0


def validate(
    answer: str,
    citations: list[str],
    context_chunks: list[dict[str, Any]],
) -> tuple[bool, list[str]]:
    if not CITATION_GUARD:
        return True, []

    if not citations:
        return True, []

    failures: list[str] = []
    for citation_text in citations:
        if not _citation_found_in_context(citation_text, context_chunks):
            failures.append(citation_text)

    global _total_citations_checked, _total_citations_rejected
    with _metrics_lock:
        _total_citations_checked += len(citations)
        _total_citations_rejected += len(failures)
        rate = _total_citations_rejected / max(_total_citations_checked, 1)
        if rate > _REJECT_RATE_ALERT_THRESHOLD:
            logger.warning(
                "Citation reject rate %.1f%% exceeds threshold of %.1f%% "
                "(checked=%d, rejected=%d)",
                rate * 100, _REJECT_RATE_ALERT_THRESHOLD * 100,
                _total_citations_checked, _total_citations_rejected,
            )

    if failures:
        logger.warning("Citation guard: %d/%d citations failed validation", len(failures), len(citations))

    # Soft block: only reject if ALL citations fail
    all_failed = len(failures) >= len(citations)
    return not all_failed, failures


def _citation_found_in_context(
    citation_text: str,
    context_chunks: list[dict[str, Any]],
) -> bool:
    citation_tokens = set(_tokenize(citation_text))
    if not citation_tokens:
        return True

    for chunk in context_chunks:
        chunk_tokens = set(_tokenize(chunk.get("text", "")))
        if not chunk_tokens:
            continue
        overlap = len(citation_tokens & chunk_tokens)
        if overlap / len(citation_tokens) >= _TOKEN_OVERLAP_THRESHOLD:
            return True
    return False


def _tokenize(text: str) -> list[str]:
    import re
    return re.findall(r"\w+", text.lower())
