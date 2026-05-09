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
    "cancellation_save": {
        "INTENT_DETECTED": ["VALIDATING", "ESCALATED"],
        "VALIDATING": ["CLASSIFYING_INTENT", "FAILED", "ESCALATED"],
        "CLASSIFYING_INTENT": ["SELECTING_SAVE_FLOW", "ESCALATED"],
        "SELECTING_SAVE_FLOW": ["SAVE_OFFER_PENDING", "ESCALATED"],
        "SAVE_OFFER_PENDING": ["SAVE_OFFER_SENT", "ESCALATED"],
        "SAVE_OFFER_SENT": ["WAITING_CUSTOMER_DECISION"],
        "WAITING_CUSTOMER_DECISION": ["EXECUTING_ACTION", "CANCELLED", "ESCALATED", "FAILED"],
        "EXECUTING_ACTION": ["RETAINED", "ESCALATED", "FAILED"],
        "RETAINED": [],
        "CANCELLED": [],
        "ESCALATED": [],
        "FAILED": [],
        "EXPIRED": [],
    },
    "wismo": {
        "INQUIRY_DETECTED": ["VALIDATING_IDENTITY", "ESCALATED"],
        "VALIDATING_IDENTITY": ["RETRIEVING_SHIPMENT", "FAILED", "ESCALATED"],
        "RETRIEVING_SHIPMENT": ["NORMALIZING_SHIPMENT_STATE", "ESCALATED"],
        "NORMALIZING_SHIPMENT_STATE": ["CLASSIFYING_RISK", "ESCALATED"],
        "CLASSIFYING_RISK": ["RESPONSE_PENDING", "ESCALATED"],
        "RESPONSE_PENDING": ["RESPONSE_SENT", "ESCALATED"],
        "RESPONSE_SENT": ["WAITING_CUSTOMER", "RESOLVED"],
        "WAITING_CUSTOMER": ["RESOLVED", "ESCALATED", "FAILED"],
        "RESOLVED": [],
        "ESCALATED": [],
        "FAILED": [],
        "EXPIRED": [],
    },
}


def validate_transition(workflow_type: str, from_state: str, to_state: str) -> bool:
    wf_map = TRANSITION_MAPS.get(workflow_type)
    if not wf_map:
        return False
    allowed = wf_map.get(from_state, [])
    return to_state in allowed
