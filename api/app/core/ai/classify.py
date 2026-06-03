from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from openai import AsyncOpenAI

from ...config import get_settings

logger = logging.getLogger(__name__)

EMERGENCY_KEYWORDS = {
    "chest pain", "can't breathe", "cannot breathe", "severe bleeding",
    "heart attack", "stroke", "suicidal", "emergency",
    "ambulance", "911", "112", "not breathing", "unconscious",
    "heavy bleeding", "head injury", "poison", "overdose",
}

HIGH_LEVEL_INTENTS = [
    "appointment", "reschedule", "cancel", "availability",
    "emergency", "billing", "prescription", "kb_query",
    "general", "campaign_positive", "campaign_negative",
    "campaign_question", "followup_feeling_good",
    "followup_feeling_bad", "followup_medication_ok",
    "followup_medication_not",
]

TRIAGE_INTENT_DESCRIPTIONS = {
    "book_appointment": "Patient wants to schedule a new appointment",
    "reschedule": "Patient wants to change an existing appointment time or date",
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


@dataclass
class ClassificationResult:
    intent: str = "general"
    triage_intent: str = "general_question"
    urgency: str = "routine"
    confidence: float = 0.0
    entities: dict = field(default_factory=dict)
    matched_keyword: str | None = None


async def classify(
    message: str,
    tenant_id: str,
    history: list[dict] | None = None,
) -> ClassificationResult:
    msg_lower = message.lower()
    for kw in EMERGENCY_KEYWORDS:
        if kw in msg_lower:
            logger.warning("classify: emergency keyword %r detected in message", kw)
            return ClassificationResult(
                intent="emergency",
                triage_intent="emergency",
                urgency="emergency",
                confidence=1.0,
                matched_keyword=kw,
            )

    prompt_parts = [
        "You are a medical triage assistant. Classify the patient's message into exactly one high-level intent and one triage intent.",
        "Also assess urgency (routine / urgent / emergency) and extract relevant entities like doctor name, date, time, symptoms.",
        "",
        "High-level intents:",
    ]
    for cat in HIGH_LEVEL_INTENTS:
        prompt_parts.append(f"- {cat}")

    prompt_parts.extend([
        "",
        "Triage intents:",
    ])
    for intent, desc in TRIAGE_INTENT_DESCRIPTIONS.items():
        prompt_parts.append(f"- {intent}: {desc}")

    if history:
        prompt_parts.append("\nConversation history (newest last):")
        for entry in history[-5:]:
            role = entry.get("role", "patient")
            content = entry.get("content", "")[:200]
            prompt_parts.append(f"- {role}: {content}")

    prompt_parts.append(f"\nPatient message: {message}")
    prompt_parts.append(
        'Respond with JSON only: {"intent": "...", "triage_intent": "...", "urgency": "...", "confidence": 0.0-1.0, "entities": {}}'
    )
    prompt = "\n".join(prompt_parts)

    try:
        client = AsyncOpenAI(api_key=get_settings().openai_api_key)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=150,
        )
        raw = response.choices[0].message.content or ""
    except Exception as e:
        logger.error("classify LLM call failed: %s", e)
        return ClassificationResult(intent="general", triage_intent="general_question", urgency="routine", confidence=0.0)

    try:
        parsed = json.loads(raw)
        return ClassificationResult(
            intent=parsed.get("intent", "general"),
            triage_intent=parsed.get("triage_intent", "general_question"),
            urgency=parsed.get("urgency", "routine"),
            confidence=parsed.get("confidence", 0.0),
            entities=parsed.get("entities", {}),
        )
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.warning("classify: failed to parse LLM response: %s", raw)
        return ClassificationResult(intent="general", triage_intent="general_question", urgency="routine", confidence=0.0)
