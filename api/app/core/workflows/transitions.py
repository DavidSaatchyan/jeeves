from __future__ import annotations

TRANSITION_MAPS: dict[str, dict[str, list[str]]] = {
    "payment_recovery": {
        "DETECTED": ["VALIDATING", "ESCALATED"],
        "VALIDATING": ["CLASSIFYING_FAILURE", "FAILED", "ESCALATED"],
        "CLASSIFYING_FAILURE": ["SELECTING_STRATEGY", "ESCALATED"],
        "SELECTING_STRATEGY": ["OUTREACH_PENDING", "RETRY_SCHEDULED", "ESCALATED"],
        "OUTREACH_PENDING": ["OUTREACH_SENT", "ESCALATED"],
        "OUTREACH_SENT": ["WAITING_CUSTOMER", "RETRY_SCHEDULED"],
        "WAITING_CUSTOMER": ["RETRY_PENDING", "RECOVERED", "ESCALATED", "RETRY_SCHEDULED"],
        "RETRY_SCHEDULED": ["RETRY_PENDING", "EXPIRED"],
        "RETRY_PENDING": ["RETRYING", "RECOVERED", "FAILED", "ESCALATED"],
        "RETRYING": ["VERIFYING_RESULT", "ESCALATED"],
        "VERIFYING_RESULT": ["RECOVERED", "WAITING_CUSTOMER", "FAILED", "PAUSED_RECONCILIATION"],
        "PAUSED_RECONCILIATION": ["VALIDATING", "ESCALATED", "FAILED"],
        "RECOVERED": [],
        "FAILED": [],
        "ESCALATED": [],
        "EXPIRED": [],
    },

}


def validate_transition(workflow_type: str, from_state: str, to_state: str) -> bool:
    wf_map = TRANSITION_MAPS.get(workflow_type)
    if not wf_map:
        return False
    allowed = wf_map.get(from_state, [])
    return to_state in allowed
