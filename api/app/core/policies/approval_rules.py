from __future__ import annotations

from .engine import PolicyEngine


def requires_approval(action: str, context: dict | None = None) -> tuple[bool, str]:
    engine = PolicyEngine(context.get("tenant_id", "")) if context else None
    if engine:
        policy = engine.evaluate("approval", {})
        approval_actions = policy.get("requires_approval", ["discount", "credit", "refund"])
    else:
        approval_actions = ["discount", "credit", "refund"]

    if action in approval_actions:
        return True, f"action_{action}_requires_merchant_approval"

    return False, ""


def get_allowed_save_actions(subscription_status: str, tenant_id: str) -> list[str]:
    engine = PolicyEngine(tenant_id)
    policy = engine.evaluate("communication", {})

    default_actions = ["pause", "skip", "delay"]
    if subscription_status != "active":
        return []

    return policy.get("allowed_save_actions", default_actions)
