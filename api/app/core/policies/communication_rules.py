from __future__ import annotations

from .engine import PolicyEngine


def check_communication_allowed(channel: str, tenant_id: str) -> tuple[bool, str]:
    engine = PolicyEngine(tenant_id)
    policy = engine.evaluate("communication", {})
    allowed_channels = policy.get("allowed_channels", ["email", "widget"])
    if channel not in allowed_channels:
        return False, f"channel_{channel}_not_allowed"
    return True, ""


def check_outreach_limit(outreach_count: int, max_outreach: int | None = None, tenant_id: str = "") -> tuple[bool, str]:
    if max_outreach is None and tenant_id:
        engine = PolicyEngine(tenant_id)
        policy = engine.evaluate("communication", {})
        max_outreach = policy.get("max_outreach", 3)
    max_outreach = max_outreach or 3
    if outreach_count >= max_outreach:
        return False, f"max_outreach_{max_outreach}_exceeded"
    return True, ""


def check_cooldown(hours_since_last: float, cooldown_hours: int | None = None, tenant_id: str = "") -> tuple[bool, str]:
    if cooldown_hours is None and tenant_id:
        engine = PolicyEngine(tenant_id)
        policy = engine.evaluate("communication", {})
        cooldown_hours = policy.get("cooldown_hours", 24)
    cooldown_hours = cooldown_hours or 24
    if hours_since_last < cooldown_hours:
        return False, f"cooldown_{cooldown_hours}h_not_elapsed"
    return True, ""
