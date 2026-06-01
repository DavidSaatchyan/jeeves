from __future__ import annotations

import base64
import logging
from typing import Any
from urllib.parse import urljoin

import httpx

from .base import AbstractCrmConnector
from .exceptions import ConnectorAuthError, ConnectorError, ConnectorNotFoundError, ConnectorRateLimitError

logger = logging.getLogger("jeeves.cliniko")

_CLINIKO_API_BASE = "https://api.{shard}.cliniko.com/v1"


class ClinikoConnector(AbstractCrmConnector):
    """Cliniko CRM connector — patients + appointments via Cliniko REST API."""

    provider = "cliniko"
    phi_safe = True

    def __init__(self, config: dict[str, Any]) -> None:
        self.api_key = str(config.get("api_key", ""))
        self.shard = str(config.get("shard", "au1"))
        self.user_agent = str(config.get("user_agent", "Jeeves (devs@jeeves.ai)"))
        self.base_url = _CLINIKO_API_BASE.format(shard=self.shard)

    def _auth_header(self) -> str:
        raw = f"{self.api_key}:"
        encoded = base64.b64encode(raw.encode()).decode()
        return f"Basic {encoded}"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self._auth_header(),
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": self.user_agent,
        }

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        try:
            r = httpx.request(method, url, headers=self._headers(), **kwargs, timeout=30)
            r.raise_for_status()
            if r.status_code == 204:
                return None
            return r.json()
        except httpx.HTTPStatusError as e:
            logger.error("cliniko API error %s %s: %s", method, path, e)
            if e.response.status_code == 401:
                raise ConnectorAuthError("cliniko", method, "Invalid API key")
            if e.response.status_code == 404:
                raise ConnectorNotFoundError("cliniko", method, f"Resource not found: {path}")
            if e.response.status_code == 429:
                raise ConnectorRateLimitError("cliniko", method, "Rate limited")
            raise ConnectorError("cliniko", method, f"HTTP {e.response.status_code}: {e.response.text[:200]}")
        except httpx.RequestError as e:
            raise ConnectorError("cliniko", "request", str(e))

    def _build_q(self, **filters: str) -> dict[str, list[str]]:
        params: dict[str, list[str]] = {}
        for field, value in filters.items():
            if value:
                params.setdefault("q[]", []).append(f"{field}:{value}")
        return params

    # Connection test

    def test_connection(self) -> bool:
        try:
            self._request("GET", "/practitioners", params={"per_page": 1})
            return True
        except Exception:
            return False

    # Practitioners

    def get_practitioners(self) -> list[dict[str, Any]]:
        """Fetch all practitioners from Cliniko."""
        result = self._request("GET", "/practitioners", params={"per_page": "100"})
        if isinstance(result, dict):
            return result.get("practitioners", [])
        return []

    def get_practitioner_by_id(self, practitioner_id: str) -> dict[str, Any] | None:
        """Fetch a single practitioner by Cliniko ID."""
        try:
            return self._request("GET", f"/practitioners/{practitioner_id}")
        except ConnectorNotFoundError:
            return None

    # Appointment Types

    def get_appointment_types(self) -> list[dict[str, Any]]:
        """Fetch all appointment types from Cliniko."""
        result = self._request("GET", "/appointment_types", params={"per_page": "100"})
        if isinstance(result, dict):
            return result.get("appointment_types", [])
        return []

    def get_appointment_type_by_id(self, type_id: str) -> dict[str, Any] | None:
        """Fetch a single appointment type by Cliniko ID."""
        try:
            return self._request("GET", f"/appointment_types/{type_id}")
        except ConnectorNotFoundError:
            return None

    # Patients

    def get_patient(self, patient_id: str) -> dict[str, Any] | None:
        try:
            return self._request("GET", f"/patients/{patient_id}")
        except ConnectorNotFoundError:
            return None

    def find_patient(self, email: str | None = None, phone: str | None = None) -> dict[str, Any] | None:
        filters: dict[str, str] = {}
        if email:
            filters["email"] = email
        elif phone:
            filters["mobile"] = phone
        else:
            return None
        q_params = self._build_q(**{f"{k}:=": v for k, v in filters.items()})
        results = self._request("GET", "/patients", params={**q_params, "per_page": "1"})
        if isinstance(results, dict):
            patients = results.get("patients", [])
            if patients:
                return patients[0]
        return None

    def create_patient(self, data: dict[str, Any]) -> dict[str, Any]:
        cliniko_data = _map_patient_to_cliniko(data)
        return self._request("POST", "/patients", json=cliniko_data)

    def update_patient(self, patient_id: str, data: dict[str, Any]) -> dict[str, Any]:
        cliniko_data = _map_patient_to_cliniko(data)
        return self._request("PUT", f"/patients/{patient_id}", json=cliniko_data)

    # Appointments

    def create_appointment(self, patient_id: str, data: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "patient_id": f"/v1/patients/{patient_id}",
            "starts_at": data.get("start_time", ""),
            "ends_at": data.get("end_time", ""),
            "notes": data.get("reason", data.get("notes", "")),
        }
        if data.get("provider_name"):
            payload["practitioner_id"] = f"/v1/practitioners/{data['provider_name']}"
        if data.get("appointment_type_id"):
            payload["appointment_type_id"] = f"/v1/appointment_types/{data['appointment_type_id']}"
        return self._request("POST", "/individual_appointments", json=payload)

    def update_appointment(self, appt_id: str, data: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if "start_time" in data:
            payload["starts_at"] = data["start_time"]
        if "end_time" in data:
            payload["ends_at"] = data["end_time"]
        if data.get("reason") or data.get("notes"):
            payload["notes"] = data.get("reason", data.get("notes", ""))
        if data.get("provider_name"):
            payload["practitioner_id"] = f"/v1/practitioners/{data['provider_name']}"
        if data.get("appointment_type_id"):
            payload["appointment_type_id"] = f"/v1/appointment_types/{data['appointment_type_id']}"
        return self._request("PUT", f"/individual_appointments/{appt_id}", json=payload)

    def cancel_appointment(self, appt_id: str) -> bool:
        try:
            from datetime import datetime
            self._request("PUT", f"/individual_appointments/{appt_id}", json={
                "cancelled_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            })
            return True
        except Exception:
            return False

    def get_appointment(self, appt_id: str) -> dict[str, Any] | None:
        try:
            return self._request("GET", f"/individual_appointments/{appt_id}")
        except ConnectorNotFoundError:
            return None

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
        filters: dict[str, str] = {}
        if date_from:
            filters["starts_at:>="] = date_from
        if date_to:
            filters["starts_at:<="] = date_to
        if patient_id:
            filters["patient_id:="] = patient_id
        if provider:
            filters["practitioner_id:="] = provider
        q_params = self._build_q(**filters)
        page = (offset // limit) + 1 if limit else 1
        params: dict[str, Any] = {**q_params, "page": str(page), "per_page": str(limit)}
        return self._request("GET", "/individual_appointments", params=params)

    def get_patient_appointments(self, patient_id: str) -> list[dict[str, Any]]:
        result = self._request("GET", "/individual_appointments", params={
            "q[]": f"patient_id:={patient_id}",
            "per_page": "100",
        })
        if isinstance(result, dict):
            return result.get("individual_appointments", [])
        return []

    # Slots

    def search_available_slots(self, doctor_id: str, date: str) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "q[]": [f"practitioner_id:={doctor_id}", f"date:={date}"],
        }
        result = self._request("GET", "/available_times", params=params)
        if isinstance(result, dict):
            return result.get("available_times", [])
        return []

    # Webhooks

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        return True

    def parse_webhook_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        event_type = payload.get("event", "unknown")
        resource = payload.get("data", payload.get("resource", {}))
        return {"event": event_type, "resource": resource}


def _map_patient_to_cliniko(data: dict[str, Any]) -> dict[str, Any]:
    mapped: dict[str, Any] = {}
    if "first_name" in data:
        mapped["first_name"] = data["first_name"]
    if "last_name" in data:
        mapped["last_name"] = data["last_name"]
    if "email" in data:
        mapped["email"] = data["email"]
    if "phone" in data:
        mapped["mobile"] = data["phone"]
    if "date_of_birth" in data:
        mapped["date_of_birth"] = data["date_of_birth"]
    if "gender" in data:
        mapped["gender"] = data["gender"]
    if "notes" in data:
        mapped["notes"] = data["notes"]
    return mapped
