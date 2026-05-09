from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .engine import PolicyEngine


def compute_retry_schedule(failure_category: str, attempt_count: int, tenant_id: str) -> dict[str, Any]:
    engine = PolicyEngine(tenant_id)
    decision = engine.evaluate("retry", {"attempt_count": attempt_count})

    if not decision["allowed"]:
        return {"should_retry": False, "reason": decision["reason"]}

    delay = decision["delay_seconds"]
    execute_at = datetime.utcnow() + timedelta(seconds=delay)

    return {
        "should_retry": True,
        "execute_at": execute_at,
        "delay_seconds": delay,
        "attempt": attempt_count + 1,
        "max_attempts": decision["max_attempts"],
    }


def is_retry_eligible(subscription_active: bool, is_duplicate: bool, is_escalated: bool) -> bool:
    if not subscription_active:
        return False
    if is_duplicate:
        return False
    if is_escalated:
        return False
    return True
