from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

EMERGENCY_KEYWORDS = {
    "chest pain", "can't breathe", "cannot breathe", "severe bleeding",
    "heart attack", "stroke", "suicidal", "emergency",
    "ambulance", "911", "112", "not breathing", "unconscious",
    "heavy bleeding", "head injury", "poison", "overdose",
}

MEDICAL_INTENTS = {
    "book_appointment": "Patient wants to schedule a new appointment",
    "reschedule": "Patient wants to change an existing appointment time",
    "cancel_appointment": "Patient wants to cancel an existing appointment",
    "check_availability": "Patient asking about available times or slots",
    "emergency": "Patient expressing urgent or emergency medical need",
    "general_question": "General clinic question about hours, location, insurance",
    "billing_question": "Question about payment, insurance, costs",
    "prescription_request": "Request for prescription refill",
    "lab_result": "Question about lab or test results",
    "follow_up": "Post-visit follow-up or question about aftercare",
    "greeting": "Greeting, small talk, thanks, unclear",
}


async def triage_intent(
    message: str,
    conversation_history: list[dict] | None = None,
    tenant_id: str | None = None,
) -> dict:
    """Classify patient message into medical intent.

    Returns:
        {"intent": "book_appointment", "urgency": "routine",
         "confidence": 0.95, "entities": {}}

    Temperature: 0.1. Fallback on LLM failure.
    """
    msg_lower = message.lower()
    for kw in EMERGENCY_KEYWORDS:
        if kw in msg_lower:
            logger.warning("triage: emergency keyword %r detected in message", kw)
            return {
                "intent": "book_appointment",
                "urgency": "emergency",
                "confidence": 1.0,
                "entities": {"matched_keyword": kw},
            }

    prompt_parts = [
        "You are a medical triage assistant. Classify the patient's message into exactly one intent.",
        "Also assess urgency (routine / urgent / emergency) and extract relevant entities like doctor name, date, time.",
        "",
        "Intents:",
    ]
    for intent, desc in MEDICAL_INTENTS.items():
        prompt_parts.append(f"- {intent}: {desc}")

    if conversation_history:
        prompt_parts.append("\nConversation history (newest last):")
        for entry in conversation_history[-5:]:
            role = entry.get("role", "patient")
            content = entry.get("content", "")[:200]
            prompt_parts.append(f"- {role}: {content}")

    prompt_parts.append(f"\nPatient message: {message}")
    prompt_parts.append(
        'Respond with JSON only: {"intent": "...", "urgency": "...", "confidence": 0.0-1.0, "entities": {}}'
    )
    prompt = "\n".join(prompt_parts)

    try:
        from openai import AsyncOpenAI
        from ...config import get_settings

        client = AsyncOpenAI(api_key=get_settings().openai_api_key)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=150,
        )
        raw = (response.choices[0].message.content or "").strip()
    except Exception:
        logger.exception("triage LLM call failed — using fallback")
        return {"intent": "general_question", "urgency": "routine", "confidence": 0.0, "entities": {}}

    try:
        parsed = json.loads(raw)
        intent = parsed.get("intent", "general_question")
        urgency = parsed.get("urgency", "routine")
        confidence = float(parsed.get("confidence", 0.0))
        entities = parsed.get("entities", {})

        if intent not in MEDICAL_INTENTS:
            intent = "general_question"

        if urgency not in ("routine", "urgent", "emergency"):
            urgency = "routine"

        logger.info("triage: intent=%s urgency=%s confidence=%.2f", intent, urgency, confidence)
        return {
            "intent": intent,
            "urgency": urgency,
            "confidence": min(max(confidence, 0.0), 1.0),
            "entities": entities,
        }
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.warning("triage: failed to parse LLM response %r — using fallback", raw)
        return {"intent": "general_question", "urgency": "routine", "confidence": 0.0, "entities": {}}
