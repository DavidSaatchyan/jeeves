from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

CATEGORIES = [
    "appointment",
    "reschedule",
    "cancel",
    "availability",
    "emergency",
    "billing",
    "prescription",
    "kb_query",
    "general",
    "campaign_positive",
    "campaign_negative",
    "campaign_question",
    "followup_feeling_good",
    "followup_feeling_bad",
    "followup_medication_ok",
    "followup_medication_not",
]

CATEGORY_DESCRIPTIONS = {
    "appointment": "Patient wants to schedule a new appointment or see a doctor",
    "reschedule": "Patient wants to change an existing appointment time or date",
    "cancel": "Patient wants to cancel an existing appointment",
    "availability": "Patient asking about available times, slots, or doctor schedules",
    "emergency": "Patient expressing urgent medical need, pain, or emergency situation",
    "billing": "Question about payment, insurance coverage, costs, or invoices",
    "prescription": "Request for prescription refill or medication question",
    "kb_query": "Patient asking for general information (policies, FAQ, hours, location)",
    "general": "Greeting, thanks, small talk, goodbye, unclear, empty",
    "campaign_positive": "Positive response to a marketing campaign offer, interested",
    "campaign_negative": "Not interested, opt-out, stop sending marketing messages",
    "campaign_question": "Asking for more information about the campaign offer",
    "followup_feeling_good": "Patient reports feeling well after a procedure or visit",
    "followup_feeling_bad": "Patient reports complications, pain, or concerns after visit",
    "followup_medication_ok": "Patient is adherent to prescribed medication",
    "followup_medication_not": "Patient is not taking medication as prescribed",
}


async def classify_intent(message: str, tenant_id: str, history: list[dict] | None = None) -> str:
    prompt_parts = [
        "Classify this medical patient message into exactly one category:",
    ]
    for cat in CATEGORIES:
        prompt_parts.append(f"- {cat}: {CATEGORY_DESCRIPTIONS[cat]}")

    if history:
        prompt_parts.append("\nConversation history (newest last):")
        for entry in history[-5:]:
            role = entry.get("role", "patient")
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

    if raw in CATEGORIES:
        logger.info("intent classifier: %r -> %s", message[:60], raw)
        return raw

    logger.info("intent classifier: unrecognized %r for %r — falling back to kb_query", raw, message[:60])
    return "kb_query"
