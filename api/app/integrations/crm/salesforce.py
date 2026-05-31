from __future__ import annotations

from typing import Any

from .base import AbstractCrmConnector
from .exceptions import CrmConnectionError


class SalesforceAdapter(AbstractCrmConnector):
    """Salesforce Health Cloud adapter — enterprise, BAA available.

    Phase 3 stub — full implementation in Phase 5+.
    """

    provider = "salesforce"
    phi_safe = True

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def get_patient(self, patient_id: str) -> dict[str, Any] | None:
        raise CrmConnectionError(self.provider, "get_patient", "Not implemented in Phase 3")

    def find_patient(self, email: str | None = None, phone: str | None = None) -> dict[str, Any] | None:
        raise CrmConnectionError(self.provider, "find_patient", "Not implemented in Phase 3")

    def create_patient(self, data: dict[str, Any]) -> dict[str, Any]:
        raise CrmConnectionError(self.provider, "create_patient", "Not implemented in Phase 3")

    def update_patient(self, patient_id: str, data: dict[str, Any]) -> dict[str, Any]:
        raise CrmConnectionError(self.provider, "update_patient", "Not implemented in Phase 3")

    def create_appointment(self, patient_id: str, data: dict[str, Any]) -> dict[str, Any]:
        raise CrmConnectionError(self.provider, "create_appointment", "Not implemented in Phase 3")

    def update_appointment(self, appt_id: str, data: dict[str, Any]) -> dict[str, Any]:
        raise CrmConnectionError(self.provider, "update_appointment", "Not implemented in Phase 3")

    def cancel_appointment(self, appt_id: str) -> bool:
        raise CrmConnectionError(self.provider, "cancel_appointment", "Not implemented in Phase 3")

    def get_patient_appointments(self, patient_id: str) -> list[dict[str, Any]]:
        raise CrmConnectionError(self.provider, "get_patient_appointments", "Not implemented in Phase 3")

    def search_available_slots(self, doctor_id: str, date: str) -> list[dict[str, Any]]:
        return []

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        return True  # Stub

    def parse_webhook_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"event": "stub", "resource": {}}
