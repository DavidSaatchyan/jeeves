from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ...db import SessionLocal
from ...models import PolicySet

_DEFAULT_RETRY = {
    "max_attempts": 3,
    "retry_windows": [300, 3600, 86400],
    "cooldown_minutes": 5,
}
_DEFAULT_COMMUNICATION = {
    "max_outreach_per_workflow": 3,
    "cooldown_between_messages": 24,
    "allowed_channels": ["email", "widget"],
}
_DEFAULT_ESCALATION = {
    "frustration_threshold": "medium",
    "max_failures_before_escalation": 3,
    "sla_hours": 24,
}
_DEFAULT_APPROVAL = {
    "requires_approval": ["discount", "credit", "refund"],
    "allowed_save_actions": ["pause", "skip", "delay"],
}


class PolicyEngine:
    def __init__(self, tenant_id: str, db: Session | None = None):
        self.tenant_id = tenant_id
        self._policy = self._load(tenant_id, db)

    def _load(self, tenant_id: str, db: Session | None = None) -> dict[str, Any]:
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True
        try:
            row = db.query(PolicySet).filter(PolicySet.tenant_id == tenant_id).first()
            if row:
                return {
                    "retry": row.retry_policy or _DEFAULT_RETRY,
                    "communication": row.communication_policy or _DEFAULT_COMMUNICATION,
                    "escalation": row.escalation_policy or _DEFAULT_ESCALATION,
                    "approval": row.approval_policy or _DEFAULT_APPROVAL,
                }
        finally:
            if close_db:
                db.close()

        return {
            "retry": _DEFAULT_RETRY,
            "communication": _DEFAULT_COMMUNICATION,
            "escalation": _DEFAULT_ESCALATION,
            "approval": _DEFAULT_APPROVAL,
        }

    def evaluate(self, policy_type: str, context: dict[str, Any]) -> dict[str, Any]:
        if policy_type == "retry":
            return self._evaluate_retry(context)
        if policy_type == "communication":
            return self._evaluate_communication(context)
        if policy_type == "escalation":
            return self._evaluate_escalation(context)
        if policy_type == "approval":
            return self._evaluate_approval(context)
        return {"allowed": True, "reason": "no_policy"}

    def _evaluate_retry(self, context: dict[str, Any]) -> dict[str, Any]:
        policies = self._policy.get("retry", _DEFAULT_RETRY)
        max_attempts = policies.get("max_attempts", 3)
        retry_windows = policies.get("retry_windows", [300, 3600, 86400])
        cooldown_minutes = policies.get("cooldown_minutes", 5)

        attempt_count = context.get("attempt_count", 0)
        if attempt_count >= max_attempts:
            return {"allowed": False, "reason": "max_attempts_exceeded", "attempt_count": attempt_count}

        window_index = min(attempt_count, len(retry_windows) - 1)
        delay_seconds = retry_windows[window_index]

        return {
            "allowed": True,
            "delay_seconds": delay_seconds,
            "attempt_count": attempt_count,
            "max_attempts": max_attempts,
            "cooldown_minutes": cooldown_minutes,
        }

    def _evaluate_communication(self, context: dict[str, Any]) -> dict[str, Any]:
        policies = self._policy.get("communication", _DEFAULT_COMMUNICATION)
        max_outreach = policies.get("max_outreach_per_workflow", 3)
        cooldown_hours = policies.get("cooldown_between_messages", 24)
        allowed_channels = policies.get("allowed_channels", ["email", "widget"])

        return {
            "allowed": True,
            "max_outreach": max_outreach,
            "cooldown_hours": cooldown_hours,
            "allowed_channels": allowed_channels,
        }

    def _evaluate_escalation(self, context: dict[str, Any]) -> dict[str, Any]:
        policies = self._policy.get("escalation", _DEFAULT_ESCALATION)
        frustration_threshold = policies.get("frustration_threshold", "medium")
        max_failures_before_escalation = policies.get("max_failures_before_escalation", 3)
        sla_hours = policies.get("sla_hours", 24)

        return {
            "frustration_threshold": frustration_threshold,
            "max_failures_before_escalation": max_failures_before_escalation,
            "sla_hours": sla_hours,
        }

    def _evaluate_approval(self, context: dict[str, Any]) -> dict[str, Any]:
        policies = self._policy.get("approval", _DEFAULT_APPROVAL)
        requires_approval = policies.get("requires_approval", ["discount", "credit", "refund"])
        allowed_save_actions = policies.get("allowed_save_actions", ["pause", "skip", "delay"])

        action = context.get("action", "")
        needs_approval = action in requires_approval

        return {
            "allowed": not needs_approval,
            "needs_approval": needs_approval,
            "allowed_save_actions": allowed_save_actions,
            "requires_approval": requires_approval,
        }

    def get_policy_snapshot(self) -> dict[str, Any]:
        return {
            "retry": self._policy.get("retry", _DEFAULT_RETRY),
            "communication": self._policy.get("communication", _DEFAULT_COMMUNICATION),
            "escalation": self._policy.get("escalation", _DEFAULT_ESCALATION),
            "approval": self._policy.get("approval", _DEFAULT_APPROVAL),
        }
