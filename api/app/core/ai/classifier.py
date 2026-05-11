from __future__ import annotations

import json
import logging
from typing import Any

from ...config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()


async def classify_failure(failure_reason: str, failure_code: str = "") -> dict[str, Any]:
    prompt = (
        f"Classify this Stripe payment failure into one of three categories:\n"
        f"- recoverable: temporary issue, retry likely works (card declined, insufficient funds, try again)\n"
        f"- semi_recoverable: may resolve with customer action (expired card, authentication required, 3DS)\n"
        f"- blocked: permanent or policy failure (account closed, fraudulent, restricted currency)\n\n"
        f"Failure reason: {failure_reason}\n"
        f"Failure code: {failure_code}\n\n"
        f"Respond with JSON: {{\"category\": \"...\", \"confidence\": 0.0-1.0, \"explanation\": \"...\"}}"
    )

    result = await _call_llm(prompt)
    return _parse_result(result, "recoverable")


async def _call_llm(prompt: str) -> str:
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=_settings.openai_api_key)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        logger.error("LLM call failed: %s", e)
        return ""


def _parse_result(raw: str, default: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
        return {
            "category": parsed.get("category", default),
            "confidence": float(parsed.get("confidence", 0.0)),
            "explanation": parsed.get("explanation", ""),
        }
    except (json.JSONDecodeError, ValueError, TypeError):
        return {"category": default, "confidence": 0.0, "explanation": "parse_failed"}
