from __future__ import annotations

import asyncio
import json
import logging
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
    cache_lookup,
    cache_store,
    mmr_diversify,
    rerank_docs,
    translate_and_search,
    validate_citations,
    search as rag_search,
)
from .base import Agent, AgentAction, AgentResult
from .default_config import get_default_agent_config
from .registry import register

logger = logging.getLogger("jeeves.agents.incoming_line")


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

    cached = cache_lookup(message)
    if cached is not None:
        results = cached
    else:
        kb_fut = translate_and_search(tenant_id, message, 10, CHAT_THRESHOLD, kb_where)
        hms_fut = translate_and_search(tenant_id, message, 10, CHAT_THRESHOLD, {"source": "hms"})

        kb_results, hms_results = await asyncio.gather(kb_fut, hms_fut)

        results = _rrf_merge(kb_results, hms_results, weights=[1.0, 1.2])

        if rerank_docs:
            rerank_top_k = 15
            results = await asyncio.to_thread(rerank_docs, message, results, rerank_top_k)

        if MMR_LAMBDA > 0.0:
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
        "You are a medical clinic assistant. Extract information only from the context provided."
    )
    user_prompt = (
        "Answer the patient's question using only the knowledge base excerpts below.\n\n"
        "RULES:\n"
        "- Answer ONLY using text that appears verbatim in the context.\n"
        "- For every claim, reference the exact document by number [Document N].\n"
        "- If the context does not contain the answer, set missing_info to true.\n"
        "- Do NOT combine separate facts into relationships unless the source text explicitly states that relationship.\n"
        "- Do NOT use your training knowledge to supplement or interpret the context.\n\n"
        f"CONTEXT:\n{context}\n\n"
        f"Patient question: {message}"
    )
    from ..schemas import KBResponse

    kb_result = await call_structured(tenant_id, system_prompt, user_prompt, KBResponse, temperature=0.0)

    if kb_result is None:
        old_prompt = f"{system_prompt}\n\n{user_prompt}"
        result = await simple_llm_response(
            tenant_id, old_prompt,
            system_override=system_prompt,
            temperature=0.0,
        )
        return result.get("response", "I don't have that information."), []

    guard_passed = True
    if kb_result.citations:
        citation_texts = [c if isinstance(c, str) else str(c) for c in kb_result.citations]
        guard_passed, guard_failures = validate_citations(kb_result.answer, citation_texts, results)
        if not guard_passed:
            logger.warning("Citation guard blocked %d citations, returning fallback", len(guard_failures))
            return "I don't have that information.", []

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
