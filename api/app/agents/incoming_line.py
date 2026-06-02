from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from ..core.ai import classify_intent, simple_llm_response
from ..core.booking import get_available_slots, book_appointment
from ..integrations.resolver import get_crm_adapter_for_tenant
from ..models import Patient, Tenant
from ..rag import search as rag_search
from .base import Agent, AgentAction, AgentResult
from .default_config import get_default_agent_config
from .registry import register

logger = logging.getLogger("jeeves.agents.incoming_line")


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


async def _handle_kb_query(message: str, tenant_id: str, config: dict) -> str:
    knowledge_folders = config.get("knowledge_folders", [])
    where_clause = {"file_id": {"$in": knowledge_folders}} if knowledge_folders else None
    results = rag_search(
        tenant_id, message, top_k=5, threshold=0.8,
        where=where_clause,
    )
    if not results:
        return "I don't have that information in my knowledge base."

    context = "\n\n".join(
        f"[Source: {r.get('filename', 'unknown')}] {r.get('text', '')}"
        for r in results
    )
    kb_prompt = (
        "Answer the patient's question using the knowledge base excerpts below. "
        "If the answer is not in the excerpts, say you don't have that information."
    )
    full_prompt = f"{kb_prompt}\n\nKnowledge base:\n{context}\n\nPatient question: {message}"
    result = await simple_llm_response(
        tenant_id, full_prompt,
        system_override="You are a medical clinic assistant. Answer only from the provided context.",
    )
    return result.get("response", "I don't have that information.")


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
        practitioners = adapter.get_practitioners() or []
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

        intent = await classify_intent(message, str(tenant.id), history=history)
        logger.info("tenant=%s intent=%s msg=%.60s", tenant.id, intent, message)

        if intent == "emergency":
            return AgentResult(
                response="If this is a medical emergency, please call your local emergency services immediately.",
                escalate=True, intent=intent,
            )

        if intent in ("kb_query",):
            response_text = await _handle_kb_query(message, str(tenant.id), config)
            return AgentResult(response=response_text, intent=intent)

        if intent in ("appointment", "reschedule", "availability"):
            return await _handle_appointment(message, tenant, db, customer_id, config)

        if intent in ("cancel",):
            return AgentResult(
                response="To cancel an appointment, please provide your appointment details and I'll help you with that.",
                intent=intent,
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
        return AgentResult(
            response=result.get("response"),
            escalate=result.get("escalated", False),
            intent=intent,
        )


incoming_line = IncomingLineAgent()
register(incoming_line)
