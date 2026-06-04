from __future__ import annotations

import json
import logging
import time
from typing import Any

import tiktoken
from openai import AsyncOpenAI

from ...config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()

_MAX_CONTEXT_TOKENS = 8000
_ENCODING = tiktoken.encoding_for_model("gpt-4o-mini")


def _count_tokens(text: str) -> int:
    return len(_ENCODING.encode(text))


def truncate_history(
    messages: list[dict],
    budget: int = _MAX_CONTEXT_TOKENS,
) -> list[dict]:
    """Truncate conversation history from oldest to fit within token budget.

    Assumes messages are in chronological order (oldest first).
    Returns the suffix of messages that fits within the budget.
    """
    if not messages:
        return messages

    candidates = list(messages)
    while candidates:
        total = sum(_count_tokens(m.get("content", "")) for m in candidates)
        if total <= budget:
            return candidates
        candidates.pop(0)

    # If even the last message exceeds budget, truncate its content
    last = candidates[-1]
    content = last.get("content", "")
    encoded = _ENCODING.encode(content)
    if len(encoded) > budget:
        last["content"] = _ENCODING.decode(encoded[:budget])
    return candidates


async def translate_query(query: str) -> str:
    prompt = (
        "Translate the following text to English. "
        "If it is already in English or is a code snippet, return it unchanged. "
        "Respond with ONLY the translation, no explanation.\n\n"
        f"Text: {query}\n\n"
        "English:"
    )
    try:
        client = AsyncOpenAI(api_key=_settings.openai_api_key)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200,
        )
        translated = response.choices[0].message.content or query
    except Exception as e:
        logger.error("translate_query LLM call failed: %s", e)
        return query
    result = translated.strip()
    if result != query:
        logger.info("translated query: %r -> %r", query, result)
    return result


async def generate_email(context: dict[str, Any], template_name: str) -> str:
    prompt = (
        f"Generate a customer-friendly email based on this context:\n"
        f"Template: {template_name}\n"
        f"Context: {json.dumps(context)}\n\n"
        f"Write a concise, professional email. Max 3 paragraphs.\n"
        f"Respond with JSON: {{\"subject\": \"...\", \"body\": \"...\"}}"
    )

    try:
        client = AsyncOpenAI(api_key=_settings.openai_api_key)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=300,
        )
        raw = response.choices[0].message.content or ""
    except Exception as e:
        logger.error("email generator LLM call failed: %s", e)
        return ""

    try:
        parsed = json.loads(raw)
        return parsed.get("body", "")
    except (json.JSONDecodeError, ValueError, TypeError):
        return ""


async def simple_llm_response(tenant_id, message: str, system_override=None, conversation_history: list[dict] | None = None, temperature: float = 0.3) -> dict:
    start = time.monotonic()
    try:
        client = AsyncOpenAI(api_key=_settings.openai_api_key)
        messages = []
        if system_override:
            messages.append({"role": "system", "content": system_override})
        if conversation_history:
            budget = _MAX_CONTEXT_TOKENS
            if system_override:
                budget -= _count_tokens(system_override)
            budget -= _count_tokens(message) + 1000  # leave room for output
            messages.extend(truncate_history(conversation_history, budget))
        messages.append({"role": "user", "content": message})
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=temperature,
            max_tokens=1000,
        )
        text = response.choices[0].message.content or ""
    except Exception as e:
        logger.error("LLM call failed: %s", e)
        text = "I'm sorry, I'm having trouble processing your request."

    elapsed = int((time.monotonic() - start) * 1000)
    return {"response": text, "latency_ms": elapsed, "escalated": False}


async def generate_widget_message(context: dict[str, Any], template_name: str) -> str:
    prompt = (
        f"Generate a short, conversational widget message based on:\n"
        f"Template: {template_name}\n"
        f"Context: {json.dumps(context)}\n\n"
        f"Write 1-2 short sentences, conversational tone, max 100 chars.\n"
        f"Respond with JSON: {{\"message\": \"...\"}}"
    )

    try:
        client = AsyncOpenAI(api_key=_settings.openai_api_key)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=150,
        )
        raw = response.choices[0].message.content or ""
    except Exception as e:
        logger.error("widget message generator LLM call failed: %s", e)
        return ""

    try:
        parsed = json.loads(raw)
        return parsed.get("message", "")
    except (json.JSONDecodeError, ValueError, TypeError):
        return ""


async def generate_campaign_message(
    tenant_id,
    campaign_context: dict,
    patient_name: str,
    conversation_history: list[dict] | None = None,
) -> str:
    """Generate a personalized campaign message using LLM.

    Temperature: 0.3. Fallback: static campaign template.
    """
    system_prompt = (
        "You are a medical clinic marketing assistant. Generate a friendly, "
        "professional campaign message for a patient. "
        "Keep it concise (2-3 sentences). "
        "Do NOT make specific medical claims or promises. "
        "Include an opt-out notice at the end."
    )
    context_str = json.dumps(campaign_context)
    user_msg = (
        f"Campaign context: {context_str}\n"
        f"Patient name: {patient_name}\n\n"
        f"Generate a personalized campaign message."
    )
    history = conversation_history or []

    try:
        client = AsyncOpenAI(api_key=_settings.openai_api_key)
        messages = [{"role": "system", "content": system_prompt}]
        budget = _MAX_CONTEXT_TOKENS - _count_tokens(system_prompt) - _count_tokens(user_msg) - 200
        messages.extend(truncate_history(history, budget))
        messages.append({"role": "user", "content": user_msg})
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.3,
            max_tokens=200,
        )
        text = response.choices[0].message.content or ""
        if text:
            return text
    except Exception as e:
        logger.error("campaign message generation failed: %s", e)

    return (
        f"Hi {patient_name}! We have some great health services available for you. "
        f"Would you like to learn more? Reply STOP to opt out."
    )
