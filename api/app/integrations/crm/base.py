from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AbstractCrmConnector(ABC):
    """Abstract base for all CRM adapters.

    Each adapter implements the methods below. Adapters that have a signed BAA
    (e.g. Zoho, Salesforce) may pass PHI through; those without (HubSpot) MUST
    return empty data or raise for PHI-sensitive operations.
    """

    provider: str
    phi_safe: bool = False  # True if BAA is signed and PHI transfer is allowed

    @abstractmethod
    def __init__(self, config: dict[str, Any]) -> None:
        ...

    # ── Patients ────────────────────────────────────────────────

    @abstractmethod
    def get_patient(self, patient_id: str) -> dict[str, Any] | None:
        ...

    @abstractmethod
    def find_patient(
        self, email: str | None = None, phone: str | None = None
    ) -> dict[str, Any] | None:
        ...

    @abstractmethod
    def create_patient(self, data: dict[str, Any]) -> dict[str, Any]:
        ...

    @abstractmethod
    def update_patient(self, patient_id: str, data: dict[str, Any]) -> dict[str, Any]:
        ...

    # ── Appointments ────────────────────────────────────────────

    @abstractmethod
    def create_appointment(self, patient_id: str, data: dict[str, Any]) -> dict[str, Any]:
        ...

    @abstractmethod
    def update_appointment(self, appt_id: str, data: dict[str, Any]) -> dict[str, Any]:
        ...

    @abstractmethod
    def cancel_appointment(self, appt_id: str) -> bool:
        ...

    @abstractmethod
    def get_patient_appointments(self, patient_id: str) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def get_appointment(self, appt_id: str) -> dict[str, Any] | None:
        """Get single appointment by external CRM ID."""
        ...

    @abstractmethod
    def list_appointments(
        self,
        tenant_id: str,
        status: str | None = None,
        provider: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        patient_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict:
        """List appointments with filters. Returns dict with total + items."""
        ...

    # ── Slots / Scheduling ──────────────────────────────────────

    @abstractmethod
    def search_available_slots(self, doctor_id: str, date: str) -> list[dict[str, Any]]:
        ...

    # ── Webhooks ─────────────────────────────────────────────────

    @abstractmethod
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        ...

    @abstractmethod
    def parse_webhook_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...
