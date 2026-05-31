from __future__ import annotations

from .appointment import TRANSITION_TABLE as APPOINTMENT_TABLE
from .marketing import TRANSITION_TABLE as MARKETING_TABLE
from .followup import TRANSITION_TABLE as FOLLOWUP_TABLE

TRANSITION_TABLES: dict[str, dict[str, list[str]]] = {
    "appointment": APPOINTMENT_TABLE,
    "marketing": MARKETING_TABLE,
    "followup": FOLLOWUP_TABLE,
}


def validate_transition(workflow_type: str, from_state: str, to_state: str) -> bool:
    table = TRANSITION_TABLES.get(workflow_type)
    if table is None:
        return False
    allowed = table.get(from_state, [])
    return to_state in allowed
