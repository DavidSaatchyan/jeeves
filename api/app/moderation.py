"""Content safety moderation — checks user input and LLM output.

Uses OpenAI Moderation API when available, falls back to keyword filter.
"""
from __future__ import annotations

import re
from typing import Any

# High-signal blocklist for fallback moderation
_BLOCKED_PATTERNS = [
    # Hate / harassment
    r"\b(hate\s+(speech|crime))\b",
    r"\b(genocide|holocaust\s+denial)\b",
    # Self-harm
    r"\b(self[-\s]?harm|suicide\s+(method|how\s+to))\b",
    # Sexual violence
    r"\b(child\s+(abuse|porn)|pedophilia)\b",
    # Violence
    r"\b(mass\s+(shooting|murder)|how\s+to\s+(make|build)\s+(a\s+)?bomb)\b",
    r"\b(how\s+to\s+(commit|make)\s+(suicide|self[-\s]?harm))\b",
    # Code injection / SSRF attempts (catches obvious attempts in chat)
    r"<script\b",
    r"javascript\s*:",
    r"data\s*:\s*text/html",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _BLOCKED_PATTERNS]

_MODERATION_CACHE: dict[str, Any] = {}


def _get_openai_moderator():
    if "moderator" in _MODERATION_CACHE:
        return _MODERATION_CACHE["moderator"]
    try:
        from openai import OpenAI
        from .config import get_settings
        settings = get_settings()
        if not settings.openai_api_key:
            return None
        client = OpenAI(api_key=settings.openai_api_key)
        _MODERATION_CACHE["moderator"] = client
        return client
    except Exception:
        return None


def _check_keywords(text: str) -> tuple[bool, str]:
    """Return (flagged, category) using keyword filter."""
    for pat in _COMPILED:
        if pat.search(text):
            return True, "keyword_match"
    return False, ""


def moderate(text: str) -> tuple[bool, str]:
    """Check text for policy violations. Returns (flagged, category)."""
    if not text or len(text.strip()) < 3:
        return False, ""

    # Try OpenAI Moderation API first
    client = _get_openai_moderator()
    if client:
        try:
            result = client.moderations.create(input=text)
            flagged = result.results[0].flagged
            if flagged:
                cats = result.results[0].categories.model_dump()
                top = max((k for k, v in cats.items() if v), key=lambda k: k)
                return True, f"openai:{top}"
        except Exception:
            pass

    # Fallback to keyword filter
    return _check_keywords(text)
