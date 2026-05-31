from __future__ import annotations

from typing import Any

import httpx

from .base import AbstractCrmConnector
from .exceptions import CrmConnectionError, CrmNotFoundError


class HubSpotAdapter(AbstractCrmConnector):
    """HubSpot CRM adapter — non-PHI marketing operations only.

    No BAA available on standard plans. PHI operations raise CrmConnectionError.
    Uses Private App token or OAuth 2.0 access token.
    """

    provider = "hubspot"
    phi_safe = False

    def __init__(self, config: dict[str, Any]) -> None:
        self.access_token: str = config["access_token"]
        self.portal_id: str = config.get("portal_id", "")

    def _api_request(self, method: str, path: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"https://api.hubapi.com{path}"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        resp = httpx.request(method, url, json=data, headers=headers, timeout=30)
        if resp.status_code == 404:
            raise CrmNotFoundError(self.provider, method, f"Resource not found: {path}")
        if resp.status_code >= 400:
            raise CrmConnectionError(self.provider, method, f"{resp.status_code}: {resp.text}")
        return resp.json()

    def get_patient(self, patient_id: str) -> dict[str, Any] | None:
        raise CrmConnectionError(self.provider, "get_patient", "PHI not allowed on HubSpot")

    def find_patient(self, email: str | None = None, phone: str | None = None) -> dict[str, Any] | None:
        raise CrmConnectionError(self.provider, "find_patient", "PHI not allowed on HubSpot")

    def create_patient(self, data: dict[str, Any]) -> dict[str, Any]:
        raise CrmConnectionError(self.provider, "create_patient", "PHI not allowed on HubSpot")

    def update_patient(self, patient_id: str, data: dict[str, Any]) -> dict[str, Any]:
        raise CrmConnectionError(self.provider, "update_patient", "PHI not allowed on HubSpot")

    def create_appointment(self, patient_id: str, data: dict[str, Any]) -> dict[str, Any]:
        # Appointments are tracked via HubSpot Meetings / Engagement
        body = {
            "engagement": {"type": "MEETING"},
            "associations": {"contactIds": [int(patient_id)]},
            "metadata": {
                "body": data.get("reason", ""),
                "startTime": data.get("start_time", ""),
                "endTime": data.get("end_time", ""),
                "title": f"Appointment with {data.get('provider_name', 'Doctor')}",
            },
        }
        return self._api_request("POST", "/engagements/v1/engagements", body)

    def update_appointment(self, appt_id: str, data: dict[str, Any]) -> dict[str, Any]:
        raise CrmConnectionError(self.provider, "update_appointment", "Not implemented for HubSpot")

    def cancel_appointment(self, appt_id: str) -> bool:
        raise CrmConnectionError(self.provider, "cancel_appointment", "Not implemented for HubSpot")

    def get_patient_appointments(self, patient_id: str) -> list[dict[str, Any]]:
        raise CrmConnectionError(self.provider, "get_patient_appointments", "Not implemented for HubSpot")

    def search_available_slots(self, doctor_id: str, date: str) -> list[dict[str, Any]]:
        return []

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        import hashlib
        import hmac
        from ...config import get_settings
        expected = hmac.new(
            get_settings().fernet_key.encode(), payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def parse_webhook_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "event": payload.get("subscriptionType", "unknown"),
            "resource": payload.get("objectId", {}),
        }
