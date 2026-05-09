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


async def classify_intent(customer_message: str) -> dict[str, Any]:
    prompt = (
        f"Classify this customer message into one of:\n"
        f"- soft_intent: customer is considering cancelling but open to solutions\n"
        f"- hard_intent: customer has decided to cancel, firm language\n"
        f"- billing_problem: issue is about billing/payment, not cancellation desire\n"
        f"- not_cancellation: message is not about cancellation at all\n\n"
        f"Message: {customer_message}\n\n"
        f"Respond with JSON: {{\"category\": \"...\", \"confidence\": 0.0-1.0, \"explanation\": \"...\"}}"
    )

    result = await _call_llm(prompt)
    return _parse_result(result, "not_cancellation")


async def classify_wismo_risk(customer_message: str, shipment_status: str) -> dict[str, Any]:
    prompt = (
        f"Classify this WISMO (Where Is My Order) inquiry into:\n"
        f"- simple_wismo: routine tracking inquiry, normal delay\n"
        f"- delay_concern: shipment is delayed beyond expected window, customer is worried\n"
        f"- escalation_risk: shipment is significantly late or has exception, customer is frustrated\n\n"
        f"Customer message: {customer_message}\n"
        f"Shipment status: {shipment_status}\n\n"
        f"Respond with JSON: {{\"category\": \"...\", \"confidence\": 0.0-1.0, \"explanation\": \"...\"}}"
    )

    result = await _call_llm(prompt)
    return _parse_result(result, "simple_wismo")


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
