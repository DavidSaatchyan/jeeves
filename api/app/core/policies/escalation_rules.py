from __future__ import annotations

from typing import Optional
from .engine import PolicyEngine


async def should_escalate(
    tenant_id: str,
    frustration_level: str = "none",
    failure_count: int = 0,
    amount: float = 0,
    is_duplicate: bool = False,
    workflow_type: str = "",
    reason: str = "",
    customer_id: str = "",
) -> bool:
    engine = PolicyEngine(tenant_id)
    policy = engine.evaluate("escalation", {})

    threshold = policy.get("frustration_threshold", "medium")
    levels = {"none": 0, "low": 1, "medium": 2, "high": 3}
    if levels.get(frustration_level, 0) >= levels.get(threshold, 2):
        return True

    max_failures = policy.get("max_failures_before_escalation", 3)
    if failure_count >= max_failures:
        return True

    amount_threshold = policy.get("amount_threshold", 300)
    if amount >= amount_threshold:
        return True

    if is_duplicate:
        return True

    return False


def should_escalate_conflict(conflict_type: str, tenant_id: str) -> tuple[bool, str]:
    engine = PolicyEngine(tenant_id)
    policy = engine.evaluate("escalation", {})

    conflict_triggers = policy.get("conflict_triggers", ["reconciliation"])
    if conflict_type in conflict_triggers:
        return True, f"conflict_detected_{conflict_type}"

    return False, ""


def should_escalate_conflict(conflict_type: str, tenant_id: str) -> tuple[bool, str]:
    engine = PolicyEngine(tenant_id)
    policy = engine.evaluate("escalation", {})

    conflict_triggers = policy.get("conflict_triggers", ["reconciliation"])
    if conflict_type in conflict_triggers:
        return True, f"conflict_detected_{conflict_type}"

    return False, ""
