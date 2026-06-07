from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncGenerator, TypeVar

import tiktoken
from openai import AsyncOpenAI
from pydantic import BaseModel

from ...config import get_settings, get_yaml_config
from ...schemas import KBResponse

logger = logging.getLogger(__name__)

_settings = get_settings()

_MAX_CONTEXT_TOKENS = 8000
_ENCODING = tiktoken.encoding_for_model("gpt-4o-mini")

_MAX_RETRIES = 1


def _get_llm_config() -> dict:
    cfg = get_yaml_config().get("llm_provider", {}) or {}
    return {
        "provider": (cfg.get("provider") or "openai").strip(),
    }


def get_llm_client(provider: str | None = None) -> Any:
    p = provider or _get_llm_config()["provider"]
    if p == "azure":
        return AsyncAzureOpenAI(
            api_key=_settings.azure_api_key,
            azure_endpoint=_settings.azure_endpoint,
            api_version=_settings.azure_api_version,
        )
    elif p == "bedrock":
        return AsyncOpenAI(
            api_key=_settings.bedrock_access_key,
            base_url=f"https://bedrock-runtime.{_settings.bedrock_region}.amazonaws.com/model/{_settings.bedrock_model_id}/invoke",
        )
    return AsyncOpenAI(api_key=_settings.openai_api_key)


def _get_fallback_provider() -> str | None:
    p = _get_llm_config()["provider"]
    if p == "openai":
        if _settings.azure_api_key and _settings.azure_endpoint:
            return "azure"
        return None
    return "openai"


async def _call_with_fallback(
    fn_name: str,
    llm_call,
    allow_fallback: bool = True,
) -> Any:
    primary = _get_llm_config()["provider"]
    for attempt in range(1 + _MAX_RETRIES):
        try:
            return await llm_call(primary)
        except Exception as e:
            logger.warning("%s failed (provider=%s attempt=%d): %s", fn_name, primary, attempt + 1, e)
            if attempt < _MAX_RETRIES:
                continue
            if not allow_fallback:
                raise
            fallback = _get_fallback_provider()
            if not fallback:
                raise
            logger.info("%s falling back to provider=%s", fn_name, fallback)
            for attempt2 in range(1 + _MAX_RETRIES):
                try:
                    return await llm_call(fallback)
                except Exception as e2:
                    logger.warning("%s failed (provider=%s attempt=%d): %s", fn_name, fallback, attempt2 + 1, e2)
                    if attempt2 < _MAX_RETRIES:
                        continue
                    raise
            break
    return None


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
        async def _call(provider: str) -> str:
            client = get_llm_client(provider)
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=200,
            )
            return response.choices[0].message.content or query
        translated = await _call_with_fallback("translate_query", _call)
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
        async def _call(provider: str) -> str:
            client = get_llm_client(provider)
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300,
            )
            return response.choices[0].message.content or ""
        raw = await _call_with_fallback("generate_email", _call)
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
        async def _call(provider: str) -> str:
            client = get_llm_client(provider)
            messages = []
            if system_override:
                messages.append({"role": "system", "content": system_override})
            if conversation_history:
                budget = _MAX_CONTEXT_TOKENS
                if system_override:
                    budget -= _count_tokens(system_override)
                budget -= _count_tokens(message) + 1000
                messages.extend(truncate_history(conversation_history, budget))
            messages.append({"role": "user", "content": message})
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=temperature,
                max_tokens=1000,
            )
            return response.choices[0].message.content or ""
        text = await _call_with_fallback("simple_llm_response", _call)
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
        async def _call(provider: str) -> str:
            client = get_llm_client(provider)
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=150,
            )
            return response.choices[0].message.content or ""
        raw = await _call_with_fallback("generate_widget_message", _call)
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
        async def _call(provider: str) -> str:
            client = get_llm_client(provider)
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
            return response.choices[0].message.content or ""
        text = await _call_with_fallback("generate_campaign_message", _call)
        if text:
            return text
    except Exception as e:
        logger.error("campaign message generation failed: %s", e)

    return (
        f"Hi {patient_name}! We have some great health services available for you. "
        f"Would you like to learn more? Reply STOP to opt out."
    )


async def naturalize_answer(tenant_id: str, cited_answer: str) -> str:
    if not cited_answer:
        return cited_answer
    try:
        async def _call(provider: str) -> str:
            client = get_llm_client(provider)
            system_msg = (
                "You are a medical answer synthesizer. "
                "Take the detailed analysis below and produce a single, coherent, "
                "natural-sounding final answer for the patient."
            )
            user_msg = (
                "The text below is a thorough step-by-step analysis with citations. "
                "Your job is to distill it into ONE clear final answer.\n\n"
                "RULES:\n"
                "- State the conclusion directly\n"
                "- Include ALL relevant facts and numbers\n"
                "- Remove any citation markers like [1], [Document 2], or quotation marks\n"
                "- Remove any internal reasoning, self-correction, or tentative language\n"
                "- Keep every factual detail\n"
                "- Sound natural and conversational\n\n"
                "Analysis:\n" + cited_answer
            )
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": system_msg}, {"role": "user", "content": user_msg}],
                temperature=0.0,
                max_tokens=1000,
            )
            return response.choices[0].message.content or ""
        cleaned = await _call_with_fallback("naturalize_answer", _call)
        return cleaned.strip()
    except Exception:
        logger.warning("naturalize_answer failed, returning original", exc_info=True)
        return cited_answer


T = TypeVar("T", bound=BaseModel)


async def call_structured(
    tenant_id: str,
    system_prompt: str,
    user_message: str,
    response_model: type[T],
    temperature: float = 0.0,
) -> T | None:
    try:
        async def _call(provider: str) -> T:
            client = get_llm_client(provider)
            completion = await client.chat.completions.parse(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                response_format=response_model,
                temperature=temperature,
                max_tokens=1000,
            )
            return completion.choices[0].message.parsed
        return await _call_with_fallback("call_structured", _call)
    except Exception as e:
        logger.error("call_structured failed: %s", e)
        return None


async def stream_llm_response(
    message: str,
    system_override: str | None = None,
    conversation_history: list[dict] | None = None,
    temperature: float = 0.3,
) -> AsyncGenerator[str, None]:
    """Stream LLM response token by token (SSE). No retry/fallback for streaming."""
    try:
        client = get_llm_client()
    except Exception as e:
        logger.error("stream_llm_response: failed to create client: %s", e)
        return

    messages: list[dict] = []
    if system_override:
        messages.append({"role": "system", "content": system_override})
    if conversation_history:
        budget = _MAX_CONTEXT_TOKENS
        if system_override:
            budget -= _count_tokens(system_override)
        budget -= _count_tokens(message) + 1000
        messages.extend(truncate_history(conversation_history, budget))
    messages.append({"role": "user", "content": message})

    try:
        stream = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=temperature,
            max_tokens=1000,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content
    except Exception as e:
        logger.error("stream_llm_response failed: %s", e)
        yield "I'm sorry, I'm having trouble processing your request."


def deterministic_naturalize(kb: KBResponse) -> str:
    """Convert structured KBResponse into a natural language answer.

    Template-based — no LLM call. Uses the structured answer + citations
    to produce a clean, conversational response.
    """
    if kb.missing_info or kb.confidence == "none":
        return "I don't have that information in my knowledge base."

    parts: list[str] = [kb.answer]

    if kb.citations:
        parts.append("")
        parts.append("Sources:")
        for i, citation in enumerate(kb.citations, 1):
            parts.append(f"{i}. {citation}")

    return "\n".join(parts)
