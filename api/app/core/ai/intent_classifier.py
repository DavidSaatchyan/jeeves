from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def classify_intent(message: str, tenant_id: str, history: list[dict] | None = None) -> str:
    prompt_parts = [
        "Classify this customer message into exactly one category:",
        "- wismo: customer asking about order status, tracking, delivery time, "
        '"where is my order", "has it shipped", tracking number, package location',
        "- kb_query: customer asking for information (policies, FAQ, product info, "
        "how-to questions, prices, features)",
        "- general: greeting, thanks, small talk, goodbye, unclear, empty",
    ]

    if history:
        prompt_parts.append("\nConversation history (newest last):")
        for entry in history:
            role = entry.get("role", "customer")
            content = entry.get("content", "")[:200]
            prompt_parts.append(f"- {role}: {content}")

    prompt_parts.append(f"\nCurrent message: {message}")
    prompt_parts.append("Category:")
    prompt = "\n".join(prompt_parts)

    try:
        from openai import AsyncOpenAI

        from ...config import get_settings

        client = AsyncOpenAI(api_key=get_settings().openai_api_key)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=20,
        )
        raw = (response.choices[0].message.content or "").strip().lower()
    except Exception:
        logger.exception("intent classifier LLM call failed — falling back to kb_query")
        return "kb_query"

    if raw in ("wismo", "kb_query", "general"):
        logger.info("intent classifier: %r -> %s", message[:60], raw)
        return raw

    logger.info("intent classifier: unrecognized %r for %r — falling back to kb_query", raw, message[:60])
    return "kb_query"
