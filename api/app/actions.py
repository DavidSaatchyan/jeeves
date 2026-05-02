"""Agent actions (FR-4.4). In MVP: update_tariff, get_subscription_status, escalate_to_human."""
from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from . import crm

# Tool schemas in OpenAI function-calling format.
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_subscription_status",
            "description": "Get customer's subscription status / tariff from the CRM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "Customer identifier"},
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_tariff",
            "description": "Change the customer's tariff/plan in the CRM. Use when user asks to switch plan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "tariff": {"type": "string", "description": "new tariff name, e.g. business"},
                    "confirmed_by_user": {
                        "type": "boolean",
                        "description": "true only after the user explicitly confirmed the plan change in the current conversation",
                    },
                },
                "required": ["user_id", "tariff", "confirmed_by_user"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": "Escalate the dialog to a human operator.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string"},
                },
                "required": ["reason"],
            },
        },
    },
]


async def dispatch(
    db: Session,
    tenant_id: UUID,
    name: str,
    args: dict[str, Any],
    fallback_user_id: str,
) -> dict:
    user_id = args.get("user_id") or fallback_user_id
    started = time.perf_counter()
    try:
        if name == "get_subscription_status":
            result = await crm.read_customer(db, tenant_id, user_id)
        elif name == "update_tariff":
            cfg = crm.get_config(db, tenant_id)
            if crm.capabilities(cfg).get("require_confirmation", True) and args.get("confirmed_by_user") is not True:
                result = {
                    "error": "confirmation_required",
                    "message": "Ask the user to explicitly confirm this plan change before calling update_tariff.",
                }
            else:
                result = await crm.write_customer(db, tenant_id, user_id, {"tariff": args.get("tariff")})
        elif name == "escalate_to_human":
            result = {"escalated": True, "reason": args.get("reason", "user request")}
        else:
            result = {"error": f"unknown action {name}"}

        crm.log_action(
            db,
            tenant_id,
            user_id,
            name,
            "failed" if isinstance(result, dict) and result.get("error") else "ok",
            request={k: v for k, v in args.items() if k != "headers"},
            response=result,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        return result
    except Exception as e:
        crm.log_action(
            db,
            tenant_id,
            user_id,
            name,
            "failed",
            request={k: v for k, v in args.items() if k != "headers"},
            error=str(e),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        raise
