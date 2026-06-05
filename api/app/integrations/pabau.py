from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any
from urllib.parse import urljoin

import httpx

from .base import AbstractCrmConnector
from .exceptions import ConnectorAuthError, ConnectorError, ConnectorNotFoundError, ConnectorRateLimitError

logger = logging.getLogger("jeeves.pabau")

_PABAU_API_BASE = "https://api.oauth.pabau.com"


class PabauConnector(AbstractCrmConnector):
    """Pabau CRM connector — patients + appointments via Pabau REST API."""

    provider = "pabau"
    phi_safe = True

    def __init__(self, config: dict[str, Any]) -> None:
        self.api_key = str(config.get("api_key", ""))
        self.company_id = str(config.get("company_id", ""))
        self.webhook_secret = str(config.get("webhook_secret", ""))
        self.base_url = str(config.get("base_url", _PABAU_API_BASE)).rstrip("/")

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.company_id:
            headers["X-Company-Id"] = self.company_id
        return headers

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = urljoin(self.base_url + "/", f"{self.api_key}/{path.lstrip('/')}")
        try:
            r = httpx.request(method, url, headers=self._headers(), **kwargs, timeout=30)
            r.raise_for_status()
            if r.status_code == 204:
                return None
            return r.json()
        except httpx.HTTPStatusError as e:
            logger.error("pabau API error %s %s: %s", method, path, e)
            if e.response.status_code == 401:
                raise ConnectorAuthError("pabau", method, "Invalid API key or company ID")
            if e.response.status_code == 404:
                raise ConnectorNotFoundError("pabau", method, f"Resource not found: {path}")
            if e.response.status_code == 429:
                raise ConnectorRateLimitError("pabau", method, "Rate limited")
            raise ConnectorError("pabau", method, f"HTTP {e.response.status_code}: {e.response.text[:200]}")
        except httpx.RequestError as e:
            raise ConnectorError("pabau", "request", str(e))

    # Practitioners

    def get_practitioners(self) -> list[dict[str, Any]]:
        result = self._request("GET", "/staff", params={"limit": 100})
        if isinstance(result, dict):
            return result.get("items", result.get("data", []))
        if isinstance(result, list):
            return result
        return []

    def get_services(self) -> list[dict[str, Any]]:
        result = self._request("GET", "/services", params={"limit": 100})
        if isinstance(result, dict):
            return result.get("items", result.get("data", []))
        if isinstance(result, list):
            return result
        return []

    def get_billable_items(
        self,
        item_type: str | None = None,
        updated_since: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.get_services()

    def get_businesses(self) -> list[dict[str, Any]]:
        return []

    # Patients

    def get_patient(self, patient_id: str) -> dict[str, Any] | None:
        try:
            return self._request("GET", f"/patients/{patient_id}")
        except ConnectorNotFoundError:
            return None

    def find_patient(self, email: str | None = None, phone: str | None = None) -> dict[str, Any] | None:
        params: dict[str, str] = {}
        if email:
            params["email"] = email
        if phone:
            params["phone"] = phone
        if not params:
            return None
        results = self._request("GET", "/patients", params={**params, "limit": "1"})
        if isinstance(results, dict):
            return results.get("items", results.get("data", [None]))[0]
        if isinstance(results, list) and len(results) > 0:
            return results[0]
        return None

    def create_patient(self, data: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/patients", json=data)

    def update_patient(self, patient_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", f"/patients/{patient_id}", json=data)

    # Appointments

    def create_appointment(self, patient_id: str, data: dict[str, Any]) -> dict[str, Any]:
        payload = dict(data)
        payload["patient_id"] = patient_id
        return self._request("POST", "/appointments", json=payload)

    def update_appointment(self, appt_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", f"/appointments/{appt_id}", json=data)

    def cancel_appointment(self, appt_id: str) -> bool:
        try:
            self._request("DELETE", f"/appointments/{appt_id}")
            return True
        except Exception:
            return False

    def get_appointment(self, appt_id: str) -> dict[str, Any] | None:
        try:
            return self._request("GET", f"/appointments/{appt_id}")
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
        params: dict[str, Any] = {"offset": offset, "limit": limit}
        if status:
            params["status"] = status
        if provider:
            params["provider"] = provider
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        if patient_id:
            params["patient_id"] = patient_id
        result = self._request("GET", "/appointments", params=params)
        if isinstance(result, dict) and "items" not in result:
            data = result.get("appointments") or result.get("data") or []
            total = result.get("total") or result.get("total_entries") or 0
            return {"items": data, "total": total}
        return result

    def get_patient_appointments(self, patient_id: str) -> list[dict[str, Any]]:
        result = self._request("GET", "/appointments", params={"patient_id": patient_id, "limit": 100})
        if isinstance(result, dict):
            return result.get("items", result.get("data", []))
        if isinstance(result, list):
            return result
        return []

    # Slots

    def search_available_slots(self, doctor_id: str, date: str) -> list[dict[str, Any]]:
        raise NotImplementedError("Pabau slot search not implemented — use Cliniko adapter")

    # Connection test

    def test_connection(self) -> bool:
        try:
            self._request("GET", "/patients", params={"limit": 1})
            return True
        except Exception:
            return False

    # Webhooks

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        if not self.webhook_secret:
            logger.warning("Pabau webhook_secret not configured — rejecting webhook")
            return False
        expected = hmac.new(self.webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def parse_webhook_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        event_type = payload.get("event", "unknown")
        resource = payload.get("data", payload.get("resource", {}))
        return {"event": event_type, "resource": resource}
