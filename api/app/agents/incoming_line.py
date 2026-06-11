from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from ..core.ai import classify
from ..core.ai.generator import call_structured, deterministic_naturalize, simple_llm_response
from ..core.booking import get_available_slots
from ..integrations.resolver import get_crm_adapter_for_tenant
from ..core.activity_log import log_activity
from ..models import Tenant
from ..rag import (
    CHAT_THRESHOLD,
    MMR_LAMBDA,
    TOP_K,
    cache_lookup,
    cache_store,
    mmr_diversify,
    rerank_docs,
    translate_and_search,
    validate_citations,
    validate_grounding,
)
from .base import Agent, AgentAction, AgentResult
from .default_config import get_default_agent_config
from .registry import register

logger = logging.getLogger("jeeves.agents.incoming_line")

_structured_failure_count: list[int] = [0]


def _rrf_merge(*lists: list[dict], weights: list[float] | None = None, k: int = 60) -> list[dict]:
    scores: dict[str, float] = {}
    items: dict[str, dict] = {}
    w = weights or [1.0] * len(lists)
    for rank_list, weight in zip(lists, w):
        for i, item in enumerate(rank_list):
            key = item.get("chunk_hash", item.get("id", str(i)))
            scores[key] = scores.get(key, 0.0) + weight / (k + i + 1)
            items[key] = item
    return sorted(items.values(), key=lambda x: scores.get(x.get("chunk_hash", ""), 0), reverse=True)


def _diversify_results(results: list[dict], key_fn: Any, max_per_group: int = 3) -> list[dict]:
    counts: dict[str, int] = {}
    out: list[dict] = []
    for r in results:
        key = key_fn(r)
        if counts.get(key, 0) < max_per_group:
            out.append(r)
            counts[key] = counts.get(key, 0) + 1
    return out


_AGGREGATION_PATTERNS = re.compile(
    r"^(?:list|what|name|tell|show|find|give|all)\b.*"
    r"(?:available|offer|provide|have|exist|service|services|price|prices|cost|costs|"
    r"procedure|procedures|vaccine|vaccines|treatment|treatments|type|types|"
    r"do you|can you|do i)",
    re.IGNORECASE,
)


def _is_aggregation_query(message: str) -> bool:
    """Detect queries that need full enumeration rather than a single answer."""
    msg = message.strip().lower()
    if not msg:
        return False
    return bool(_AGGREGATION_PATTERNS.match(msg))


def _verify_against_context(answer: str, context_chunks: list[dict]) -> bool:
    """Quick entity-level check that answer claims exist in context (zero LLM cost)."""
    phrases = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', answer)
    if not phrases:
        return True
    context_text = " ".join(c.get("text", "") for c in context_chunks).lower()
    for phrase in phrases:
        if phrase.lower() not in context_text:
            if any(phrase.lower().startswith(skip) for skip in ("thank", "please", "your", "would", "medical emergency", "i don't have", "i'm sorry", "i am sorry", "here are", "the following", "available", "call your local", "this is")):
                continue
            logger.warning("Verify: '%s' not found in context — possible hallucination", phrase)
            return False
    return True


_NEGATION_RE = re.compile(
    r"\b(?:"
    r"(?:don'?t|do not|does not|doesn'?t)\s+(?:use|need|require|involve|include|have)"
    r"|"
    r"(?:without|excluding|except|besides|other than|apart from)\s+"
    r"|"
    r"not\s+(?:intramuscular|muscular|needle|invasive|surgical|blood)"
    r"|"
    r"(?:non-?invasive|non-?surgical|non-?needle)"
    r")\b",
    re.IGNORECASE,
)


def _detect_negation(message: str) -> tuple[str, list[str]]:
    """Detect negation in a query.

    Returns (rewritten_query, negated_terms) where rewritten_query has negation
    removed for searching, and negated_terms are what should be excluded from results.
    """
    msg = message.strip().lower()

    # Pattern: "procedures that DON'T use a needle" → search "medical procedures" exclude "needle"
    m = re.search(r"(?:don'?t|do not|does not|doesn'?t)\s+(?:use|need|require|involve|include|have)\s+(?:a|an|the|any)?\s*(\w+(?:\s+\w+)?)", msg, re.IGNORECASE)
    if m:
        negated = m.group(1).strip()
        # Rewrite: remove the negation clause
        rewritten = re.sub(
            r"(?:that|which|what)\s+" + re.escape(m.group(0)),
            "",
            msg,
            flags=re.IGNORECASE,
        ).strip()
        rewritten = re.sub(r"\b(?:that|which|what)\s*,?\s*$", "", rewritten).strip()
        if not rewritten:
            rewritten = "medical procedures treatments"
        return rewritten, [negated]

    # Pattern: "without a needle", "excluding X"
    m2 = re.search(r"\b(?:without|excluding|except|besides|other than|apart from)\s+(?:a|an|the|any)?\s*(\w+(?:\s+\w+)?)", msg, re.IGNORECASE)
    if m2:
        negated = m2.group(1).strip()
        rewritten = re.sub(r"\s*" + re.escape(m2.group(0)), "", msg).strip()
        if not rewritten:
            rewritten = "medical procedures treatments"
        return rewritten, [negated]

    # Pattern: "NOT intramuscular"
    m3 = re.search(r"\bnot\s+(\w+)", msg, re.IGNORECASE)
    if m3:
        negated = m3.group(1).strip()
        rewritten = re.sub(r"\s+not\s+" + re.escape(negated), "", msg).strip()
        if not rewritten:
            rewritten = "injection routes types procedures"
        return rewritten, [negated]

    return message, []


def _filter_negated(results: list[dict], negated_terms: list[str]) -> list[dict]:
    """Filter out search results that mention negated terms."""
    if not negated_terms or not results:
        return results

    filtered: list[dict] = []
    for r in results:
        text = (r.get("text", "") or "").lower()
        skip = False
        for term in negated_terms:
            if term.lower() in text:
                skip = True
                break
        if not skip:
            filtered.append(r)

    if filtered:
        logger.info("Negation: filtered out %d/%d results containing %s", len(results) - len(filtered), len(results), negated_terms)
    return filtered or results  # Don't return empty — keep originals if filtering removes everything


def _get_agent_config(tenant: Tenant | None) -> dict:
    if tenant and tenant.agent_config:
        cfg = dict(tenant.agent_config)
        defaults = get_default_agent_config()
        for key in defaults:
            cfg.setdefault(key, defaults[key])
        for section in ("personality", "skills", "channels"):
            if section in defaults:
                s = cfg.setdefault(section, {})
                for k, v in defaults[section].items():
                    s.setdefault(k, v)
        return cfg
    return get_default_agent_config()


def _build_slot_text(slots: list) -> str:
    if not slots:
        return "No available slots found."
    lines = ["Here are the available times:"]
    for i, s in enumerate(slots[:5], 1):
        start = s.get("start", "")
        provider = s.get("provider_name", "")
        lines.append(f"{i}. {start}" + (f" with {provider}" if provider else ""))
    return "\n".join(lines)


async def _handle_kb_query(message: str, tenant_id: str, config: dict) -> tuple[str, list[dict]]:
    knowledge_folders = config.get("knowledge_folders", [])

    kb_where: dict[str, Any] = {"source": "kb"}
    if knowledge_folders:
        kb_where["folder_id"] = {"$in": knowledge_folders}

    is_aggregation = _is_aggregation_query(message)

    # Negation detection — rewrite query and pre-filter terms
    search_query, negated_terms = _detect_negation(message)
    has_negation = bool(negated_terms)

    cached = cache_lookup(message)
    if cached is not None:
        results = cached
    else:
        search_top_k = TOP_K * 2 if (is_aggregation or has_negation) else TOP_K

        kb_fut = translate_and_search(tenant_id, search_query, search_top_k, CHAT_THRESHOLD, kb_where)
        hms_fut = translate_and_search(tenant_id, search_query, search_top_k, CHAT_THRESHOLD, {"source": "hms"})

        kb_results, hms_results = await asyncio.gather(kb_fut, hms_fut)

        results = _rrf_merge(kb_results, hms_results, weights=[1.0, 1.2])

        if has_negation:
            results = _filter_negated(results, negated_terms)

        if rerank_docs:
            rerank_top_k = 30 if is_aggregation else 15
            results = await asyncio.to_thread(rerank_docs, message, results, rerank_top_k)

        if has_negation:
            results = _filter_negated(results, negated_terms)

        if is_aggregation:
            results = _diversify_results(results, key_fn=lambda r: r.get("filename", ""), max_per_group=5)[:15]
        elif MMR_LAMBDA > 0.0:
            results = mmr_diversify(results, message, lambda_=MMR_LAMBDA, top_k=5)
        else:
            results = _diversify_results(results, key_fn=lambda r: r.get("source", ""), max_per_group=3)[:5]

        cache_store(message, results)

    if not results:
        return "I don't have that information in my knowledge base.", []

    blocks = []
    for i, r in enumerate(results, 1):
        source = r.get("filename", "?")
        section = r.get("section", "") or ""
        sect_label = f" — Section: \"{section}\"" if section else ""
        sep = "═" * 60
        blocks.append(
            f"[Document {i}] {source}{sect_label}\n"
            f"{sep}\n"
            f"{r['text']}\n"
            f"{sep}"
        )
    context = "\n\n".join(blocks)

    system_prompt = (
        "You are a medical clinic assistant. Answer using ONLY the provided context. "
        "Never use your training knowledge. "
        "If the context only mentions a city or region, say ONLY that city or region — "
        "do NOT add landmarks, descriptions, climate, history, or any other information about that location. "
        "If the context does not contain the answer, set missing_info to true."
    )
    user_prompt = (
        "Answer the patient's question using only the knowledge base excerpts below.\n\n"
        "RULES:\n"
        "- Answer ONLY using text that appears verbatim in the context.\n"
        "- For every claim, reference the exact document by number [Document N].\n"
        "- If the context does not contain the answer, set missing_info to true.\n"
        "- Do NOT combine separate facts into relationships unless the source text explicitly states that relationship.\n"
        "- NEVER use your training knowledge to supplement or interpret the context.\n"
        "- If you are asked about a location, clinic, or address, answer ONLY what is written in the context. "
        "Do NOT add any city descriptions, landmarks, climate, or cultural information.\n"
        "- If you are asked to list services, prices, or items: enumerate ALL matching items from the context. "
        "Do not leave any out.\n\n"
        "CORRECT EXAMPLE: Context says 'City: Kuala Lumpur, State: WP Kuala Lumpur'\n"
        "Answer: 'Kuala Lumpur, WP Kuala Lumpur'\n\n"
        "WRONG EXAMPLE: Adding 'Kuala Lumpur is the capital of Malaysia, known for Petronas Towers'\n\n"
        f"CONTEXT:\n{context}\n\n"
        f"Patient question: {message}"
    )
    from ..schemas import KBResponse

    kb_result = await call_structured(tenant_id, system_prompt, user_prompt, KBResponse, temperature=0.0)

    if kb_result is None:
        logger.warning(
            "Structured output failed for tenant=%s query=%.60s — returning fallback",
            tenant_id, message,
        )
        _structured_failure_count[0] += 1
        return "I don't have that information in my knowledge base.", []

    guard_passed = True
    if kb_result.citations:
        citation_texts = [c if isinstance(c, str) else str(c) for c in kb_result.citations]
        guard_passed, guard_failures = validate_citations(kb_result.answer, citation_texts, results)
        if not guard_passed:
            logger.warning("Citation guard blocked %d citations, returning fallback", len(guard_failures))
            return "I don't have that information.", []

    grounding = validate_grounding(kb_result.answer, results)
    if not grounding.passed:
        logger.warning(
            "Grounding: answer rejected (confidence=%.2f, failures=%d, entities=%s)",
            grounding.confidence, len(grounding.failures), grounding.ungrounded_entities,
        )
        if grounding.confidence < 0.5:
            return "I don't have that information.", []
        logger.info("Grounding: low confidence (%.2f) but allowing through", grounding.confidence)

    answer = deterministic_naturalize(kb_result)
    if answer:
        citations = [{"source": r.get("filename", "?"), "section": r.get("section", ""), "text_snippet": r["text"][:500], "relevance": r.get("score", 0.0)} for r in results]
        return answer, citations
    return "I don't have that information.", []


async def _handle_appointment(
    message: str,
    tenant: Tenant,
    db: Session,
    customer_id: str,
    config: dict,
) -> AgentResult:
    caps = config.get("skills", {}).get("capabilities", {})
    if not caps.get("search_slots", True):
        return AgentResult(
            response="I'm sorry, I cannot search for available slots right now.",
            escalate=True,
        )
    actions: list[AgentAction] = []
    adapter = get_crm_adapter_for_tenant(tenant)
    if not adapter:
        return AgentResult(
            response="Unable to connect to the clinic calendar right now.",
            actions=[],
        )

    try:
        services = adapter.get_services() or []
    except Exception as e:
        logger.warning("Failed to fetch CRM catalogue for tenant %s: %s", tenant.id, e)
        return AgentResult(
            response="I couldn't fetch the available services. Please try again later.",
            escalate=True,
        )

    service_names = [s.get("name", "") for s in services if s.get("name")]
    extract_prompt = (
        f"Extract appointment details from this message.\n"
        f"Available services: {', '.join(service_names)}\n\n"
        f"Message: {message}\n\n"
        f"Return JSON with keys: service, date_preference (YYYY-MM-DD or null), provider (or null)"
    )
    extraction = await simple_llm_response(
        tenant.id, extract_prompt,
        system_override="You extract appointment details as JSON. Respond with valid JSON only.",
    )

    details = json.loads(extraction.get("response", "{}"))

    service = details.get("service", "")
    preferred_date_str = details.get("date_preference") or date.today().isoformat()
    provider_name = details.get("provider")

    try:
        preferred_date = date.fromisoformat(preferred_date_str)
    except (ValueError, TypeError):
        preferred_date = date.today()

    slots = get_available_slots(
        db=db,
        tenant_id=tenant.id,
        provider_name=provider_name or "",
        specialty=service,
        day=preferred_date,
        limit=5,
    )

    if not slots:
        return AgentResult(
            response=(
                f"I'm sorry, there are no available slots for{' ' + service if service else ''} "
                f"on {preferred_date_str}. Would you like to check another date?"
            ),
            actions=actions,
        )

    slot_text = _build_slot_text(slots)
    actions.append(AgentAction(action_type="slots_offered", payload={"slots": slots}))
    return AgentResult(
        response=f"I found available slots.\n\n{slot_text}\n\nPlease let me know which time works for you.",
        actions=actions,
    )


class IncomingLineAgent(Agent):
    agent_id = "incoming_line"
    description = "Front desk — handles incoming patient messages via WhatsApp and widget"

    async def handle(
        self,
        *,
        tenant_id: str,
        customer_id: str,
        db: Session,
        **kwargs: Any,
    ) -> AgentResult:
        message: str = kwargs.get("message", "")
        history: list | None = kwargs.get("history")

        tenant = db.get(Tenant, tenant_id)
        if not tenant:
            return AgentResult(response=None, escalate=True)

        config = _get_agent_config(tenant)

        if not config.get("enabled", True):
            return AgentResult(response=None, escalate=True)

        result = await classify(message, str(tenant.id), history=history)
        intent = result.intent
        logger.info("tenant=%s intent=%s msg=%.60s", tenant.id, intent, message)

        if intent == "emergency":
            log_activity(db, tenant.id, config.get("personality", {}).get("name", "Agent"), "emergency", "Patient reported emergency", patient_reference=customer_id, api_status="success")
            return AgentResult(
                response="If this is a medical emergency, please call your local emergency services immediately.",
                escalate=True, intent=intent,
            )

        if intent in ("kb_query",):
            response_text, citations = await _handle_kb_query(message, str(tenant.id), config)
            log_activity(db, tenant.id, config.get("personality", {}).get("name", "Agent"), "kb_query", "Answered knowledge base query", patient_reference=customer_id, api_status="success")
            return AgentResult(response=response_text, intent=intent, citations=citations)

        if intent in ("appointment", "reschedule", "availability"):
            return await _handle_appointment(message, tenant, db, customer_id, config)

        if intent in ("cancel",):
            log_activity(db, tenant.id, config.get("personality", {}).get("name", "Agent"), "cancel_request", "Patient requested cancellation", patient_reference=customer_id, api_status="success")
            return AgentResult(
                response="To cancel an appointment, please provide your appointment details and I'll help you with that.",
                intent=result.intent,
            )

        personality = config.get("personality", {})
        system_prompt = personality.get(
            "system_prompt",
            "You are the front desk of a medical clinic. You help patients via WhatsApp. "
            "Be warm and professional. Never diagnose or prescribe.",
        )

        result = await simple_llm_response(
            tenant.id, message,
            system_override=system_prompt,
            conversation_history=history,
        )
        log_activity(db, tenant.id, config.get("personality", {}).get("name", "Agent"), "message_sent", f"Responded to {intent} intent", patient_reference=customer_id, api_status="success" if result.get("response") else "error")
        return AgentResult(
            response=result.get("response"),
            escalate=result.get("escalated", False),
            intent=intent,
        )


incoming_line = IncomingLineAgent()
register(incoming_line)
