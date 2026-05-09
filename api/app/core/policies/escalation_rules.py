from __future__ import annotations

from .engine import PolicyEngine


def should_escalate(frustration_level: str, failure_count: int, tenant_id: str) -> tuple[bool, str]:
    engine = PolicyEngine(tenant_id)
    policy = engine.evaluate("escalation", {})

    threshold = policy.get("frustration_threshold", "medium")
    levels = {"none": 0, "low": 1, "medium": 2, "high": 3}
    if levels.get(frustration_level, 0) >= levels.get(threshold, 2):
        return True, f"frustration_{frustration_level}_exceeds_threshold_{threshold}"

    max_failures = policy.get("max_failures_before_escalation", 3)
    if failure_count >= max_failures:
        return True, f"failure_count_{failure_count}_exceeds_max_{max_failures}"

    return False, ""


def should_escalate_conflict(conflict_type: str, tenant_id: str) -> tuple[bool, str]:
    engine = PolicyEngine(tenant_id)
    policy = engine.evaluate("escalation", {})

    conflict_triggers = policy.get("conflict_triggers", ["reconciliation"])
    if conflict_type in conflict_triggers:
        return True, f"conflict_detected_{conflict_type}"

    return False, ""
