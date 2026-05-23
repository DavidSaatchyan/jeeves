from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

RISK_FALLBACK = {
    "status": "on_track",
    "confidence": 0,
    "reason": "LLM unavailable",
    "estimated_delivery": "",
    "carrier_status": "",
}


async def classify_tracking_status(fulfillments: list[dict], order: dict | None = None) -> dict:
    """Classify tracking status as on_track / delayed / lost.

    Uses GPT-4o-mini with temperature=0.1.
    Fallback: on_track with confidence 0 (silence is safer than false alarm).
    """
    if not fulfillments:
        return {
            "status": "on_track",
            "confidence": 0,
            "reason": "no fulfillments yet",
            "estimated_delivery": "",
            "carrier_status": "not_shipped",
        }

    payload = json.dumps({
        "fulfillments": [
            {
                "tracking_number": f.get("tracking_number", ""),
                "tracking_status": f.get("tracking_status", "unknown"),
                "carrier": f.get("carrier", ""),
                "estimated_delivery": f.get("estimated_delivery", ""),
                "status": f.get("status", ""),
            }
            for f in fulfillments
        ],
        "order_created_at": (order or {}).get("created_at", ""),
    })

    prompt = (
        "Classify this shipment's tracking status into exactly one category:\n"
        "- on_track: package is moving normally, ETA is reasonable\n"
        "- delayed: package is late, ETA passed, carrier shows delay\n"
        "- lost: carrier marked as lost, no updates for 7+ days, or returned to sender\n\n"
        f"Shipment data: {payload}\n\n"
        "Respond with JSON: {\"status\": \"...\", \"confidence\": 0-100, \"reason\": \"...\", "
        "\"estimated_delivery\": \"...\", \"carrier_status\": \"...\"}"
    )

    try:
        from openai import AsyncOpenAI

        from ...config import get_settings

        client = AsyncOpenAI(api_key=get_settings().openai_api_key)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200,
        )
        raw = response.choices[0].message.content or ""
    except Exception:
        logger.exception("wismo classifier LLM call failed")
        return dict(RISK_FALLBACK)

    try:
        parsed = json.loads(raw)
        for key in ("status", "confidence", "reason", "estimated_delivery", "carrier_status"):
            if key not in parsed:
                logger.warning("wismo classifier missing key %s in response", key)
                return dict(RISK_FALLBACK)
        if parsed["status"] not in ("on_track", "delayed", "lost"):
            logger.warning("wismo classifier unknown status: %s", parsed["status"])
            return dict(RISK_FALLBACK)
        return parsed
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.exception("wismo classifier failed to parse LLM response")
        return dict(RISK_FALLBACK)
