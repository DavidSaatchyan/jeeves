"""Agent Core orchestrator (FR-4).

DEFAULT: Uses OpenAI tool-calling directly (lightweight LangChain-equivalent)
— keeps the surface small but satisfies FR-4.1..FR-4.6.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any
from uuid import UUID

from openai import OpenAI
from sqlalchemy.orm import Session

from . import actions, memory, rag
from .config import get_settings, get_yaml_config
from .crm import read_customer
from .crypto import ConnectorError
from .webhooks import fetch_incoming_webhook_context
from . import routes_tools as tools_module

_settings = get_settings()
_cfg = get_yaml_config()
_AGENT = _cfg.get("agent", {})
_LLM = _cfg.get("llm", {})
SYSTEM_PROMPT = _AGENT.get("system_prompt", "You are Jeeves, a helpful AI support agent.")
TEMPERATURE = float(_AGENT.get("temperature", 0.2))
MAX_ITERATIONS = int(_AGENT.get("max_iterations", 5))
MODEL = _LLM.get("model", "gpt-4o-mini")


def _openai() -> OpenAI:
    return OpenAI(api_key=_settings.openai_api_key)


def _ensure_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


def _source_label(i: int) -> str:
    return f"S{i + 1}"


def _format_source_block(sources: list[dict]) -> str:
    if not sources:
        return ""
    blocks: list[str] = []
    for i, src in enumerate(sources):
        sid = _source_label(i)
        page = f", page {src.get('page')}" if src.get("page") else ""
        section = f", section: {src.get('section')}" if src.get("section") else ""
        blocks.append(
            f"[{sid}] {src.get('filename') or 'unknown file'}{section}{page}, "
            f"score={src.get('score')}\n{src.get('text') or ''}"
        )
    return "\n\n".join(blocks)


def _source_log(sources: list[dict]) -> list[dict]:
    out: list[dict] = []
    for i, src in enumerate(sources):
        text = src.get("text") or ""
        out.append(
            {
                "source_id": _source_label(i),
                "file_id": src.get("file_id"),
                "filename": src.get("filename"),
                "section": src.get("section"),
                "page": src.get("page"),
                "score": src.get("score"),
                "char_start": src.get("char_start"),
                "char_end": src.get("char_end"),
                "snippet": text[:500],
            }
        )
    return out


async def run(
    db: Session,
    tenant_id: UUID,
    user_id: str,
    message: str,
    extra_fields: dict | None = None,
    session_id: UUID | None = None,
) -> dict:
    """Process one user message. Returns dict(response, action_called, escalated, latency_ms, session_id)."""
    started = time.perf_counter()

    sid = session_id or uuid.uuid4()

    # 1. Fetch incoming webhook context (best-effort, before any other context)
    webhook_ctx: dict = {}
    try:
        webhook_ctx = await fetch_incoming_webhook_context(db, tenant_id, user_id, extra_fields)
    except Exception as e:
        print(f"[agent] incoming webhook failed: {e}", flush=True)

    # 2. Retrieve RAG context
    rag_docs = await asyncio.to_thread(rag.search, tenant_id, message)
    rag_block = _format_source_block(rag_docs)
    sources = _source_log(rag_docs)

    # 3. Pull CRM context (best-effort)
    crm_ctx: dict = {}
    try:
        crm_ctx = await read_customer(db, tenant_id, user_id, extra_fields)
        crm_ctx.pop("raw", None)
    except Exception as e:
        print(f"[agent] crm read failed: {e}", flush=True)

    # 4. Build messages: system + context + history + user
    sys = (
        f"{SYSTEM_PROMPT}\n\n"
        "ROLE: You are a human customer success manager, not an AI bot. "
        "You know the product inside out based on the provided context.\n\n"
        "RULES:\n"
        "1. NEVER mention 'knowledge base', 'documents', 'context', or 'uploaded files'. "
        "If you know it from context, state it as a fact you know.\n"
        "2. Be concise and direct. If you have the answer, give it immediately.\n"
        "3. If asked for a list (e.g. 'what plans do you have'), list ALL available options "
        "found in your context. Do not ask clarifying questions if the answer is available.\n"
        "4. If you don't have the specific info, apologize and offer to connect them to a human.\n\n"
        "CRM tools may read customer data or perform account changes. Before "
        "calling a write tool such as update_tariff, summarize the exact change "
        "and get explicit user confirmation in the current conversation. Set "
        "confirmed_by_user=true only after that confirmation.\n\n"
        f"Internal Reference Data:\n{rag_block}\n\n"
        f"Webhook context: {json.dumps(webhook_ctx, ensure_ascii=False, default=str)}\n\n"
        f"CRM context for user {user_id}: {json.dumps(crm_ctx, ensure_ascii=False, default=str)}"
    )
    msgs: list[dict] = [{"role": "system", "content": sys}]
    msgs.extend(memory.history(str(tenant_id), user_id))
    msgs.append({"role": "user", "content": message})
    memory.append(str(tenant_id), user_id, "user", message)

    client = _openai()
    action_called: str | None = None
    escalated = False
    final_text: str = ""

    # Load tenant tools (built-in + custom)
    tenant_tools = await asyncio.to_thread(tools_module.get_enabled_tools, db, tenant_id)
    custom_tool_map = {t.name: t for t in tenant_tools}
    all_tool_schemas = actions.TOOL_SCHEMAS + tools_module.build_tool_schemas(tenant_tools)

    for _ in range(MAX_ITERATIONS):
        resp = await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model=MODEL,
                messages=msgs,
                tools=all_tool_schemas,
                temperature=TEMPERATURE,
            )
        )
        choice = resp.choices[0]
        m = choice.message

        if m.tool_calls:
            msgs.append(
                {
                    "role": "assistant",
                    "content": m.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in m.tool_calls
                    ],
                }
            )
            for tc in m.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                action_called = name
                if name == "escalate_to_human":
                    escalated = True
                try:
                    if name in custom_tool_map:
                        result = await tools_module.dispatch_tool(
                            db, tenant_id, custom_tool_map[name], args, fallback_user_id=user_id
                        )
                    else:
                        result = await actions.dispatch(db, tenant_id, name, args, fallback_user_id=user_id)
                except ConnectorError as e:
                    result = {"error": f"Connector error: {e}"}
                except Exception as e:
                    result = {"error": str(e)}
                msgs.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": name,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )
            continue

        final_text = _ensure_text(m.content)
        break
    else:
        # Hit iteration limit → FR-4.5 escalate
        final_text = "Let me connect you to a human operator — the request is complex."
        escalated = True
        action_called = action_called or "escalate_to_human"

    memory.append(str(tenant_id), user_id, "assistant", final_text)
    latency = int((time.perf_counter() - started) * 1000)
    return {
        "response": final_text,
        "action_called": action_called,
        "escalated": escalated,
        "latency_ms": latency,
        "sources": sources,
        "session_id": str(sid),
    }
