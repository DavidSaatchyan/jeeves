from __future__ import annotations

WISMO_TRANSITIONS: dict[str, list[str]] = {
    "INQUIRY_DETECTED": ["VALIDATING_IDENTITY", "ESCALATED"],
    "VALIDATING_IDENTITY": ["RETRIEVING_SHIPMENT", "WAITING_ORDER_SELECTION", "ESCALATED"],
    "WAITING_ORDER_SELECTION": ["RETRIEVING_SHIPMENT", "ESCALATED"],
    "RETRIEVING_SHIPMENT": ["CLASSIFYING_RISK", "ESCALATED"],
    "CLASSIFYING_RISK": ["RESPONSE_SENT", "RESOLVED", "LOST", "ESCALATED"],
    "RESPONSE_SENT": ["RESOLVED", "ESCALATED"],
    "RESOLVED": [],
    "LOST": [],
    "ESCALATED": [],
}

TRANSITION_TABLES: dict[str, dict[str, list[str]]] = {
    "wismo": WISMO_TRANSITIONS,
}


def validate_transition(workflow_type: str, from_state: str, to_state: str) -> bool:
    table = TRANSITION_TABLES.get(workflow_type)
    if table is None:
        return False
    allowed = table.get(from_state, [])
    return to_state in allowed
