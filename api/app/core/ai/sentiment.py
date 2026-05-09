from __future__ import annotations

import json
import logging
from typing import Any

from ...config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()


async def detect_frustration(customer_message: str) -> dict[str, Any]:
    prompt = (
        f"Analyze the frustration level in this customer message:\n\n"
        f"Message: {customer_message}\n\n"
        f"Respond with one of: none, low, medium, high\n"
        f"Respond with JSON: {{\"level\": \"...\", \"confidence\": 0.0-1.0, \"indicators\": [\"...\"]}}"
    )

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=_settings.openai_api_key)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=150,
        )
        raw = response.choices[0].message.content or ""
    except Exception as e:
        logger.error("sentiment LLM call failed: %s", e)
        return {"level": "none", "confidence": 0.0, "indicators": []}

    try:
        parsed = json.loads(raw)
        return {
            "level": parsed.get("level", "none"),
            "confidence": float(parsed.get("confidence", 0.0)),
            "indicators": parsed.get("indicators", []),
        }
    except (json.JSONDecodeError, ValueError, TypeError):
        return {"level": "none", "confidence": 0.0, "indicators": []}
