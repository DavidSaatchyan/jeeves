from __future__ import annotations

import json
import logging
from typing import Any

from ...config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()


async def translate_query(query: str) -> str:
    """Translate a user query to English for better RAG embedding matching.
    Returns the original query unchanged on failure.
    """
    prompt = (
        "Translate the following text to English. "
        "If it is already in English or is a code snippet, return it unchanged. "
        "Respond with ONLY the translation, no explanation.\n\n"
        f"Text: {query}\n\n"
        "English:"
    )
    try:
        from openai import AsyncOpenAI

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
        from openai import AsyncOpenAI

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


async def generate_widget_message(context: dict[str, Any], template_name: str) -> str:
    prompt = (
        f"Generate a short, conversational widget message based on:\n"
        f"Template: {template_name}\n"
        f"Context: {json.dumps(context)}\n\n"
        f"Write 1-2 short sentences, conversational tone, max 100 chars.\n"
        f"Respond with JSON: {{\"message\": \"...\"}}"
    )

    try:
        from openai import AsyncOpenAI

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
