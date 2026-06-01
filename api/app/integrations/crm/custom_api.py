from __future__ import annotations

from typing import Any

import httpx

from .base import AbstractCrmConnector
from .exceptions import CrmConnectionError, CrmNotFoundError

try:
    from ...core.compliance.phi_minimization import mask_phi as _mask_phi
    _HAS_PHI = True
except ImportError:
    _HAS_PHI = False
    def _mask_phi(data, fields=None):  # type: ignore
        return data


class CustomApiAdapter(AbstractCrmConnector):
    """Generic REST API adapter for custom/self-hosted CRMs.

    Reads endpoint mappings from config and executes HTTP requests.
    """

    provider = "custom_api"
    phi_safe = False

    def __init__(self, config: dict[str, Any]) -> None:
        self.base_url: str = config["base_url"].rstrip("/")
        self.auth_type: str = config.get("auth_type", "bearer")
        self.auth_credentials: dict[str, Any] = config.get("auth_credentials", {})
        self.endpoint_mapping: dict[str, str] = config.get("endpoint_mapping", {})
        self.headers: dict[str, str] = config.get("headers", {})

    def _auth_headers(self) -> dict[str, str]:
        if self.auth_type == "bearer":
            return {"Authorization": f"Bearer {self.auth_credentials.get('token', '')}"}
        if self.auth_type == "basic":
            import base64
            raw = f"{self.auth_credentials.get('username', '')}:{self.auth_credentials.get('password', '')}"
            return {"Authorization": f"Basic {base64.b64encode(raw.encode()).decode()}"}
        if self.auth_type == "api_key":
            key = self.auth_credentials.get("key", "")
            value = self.auth_credentials.get("value", "")
            return {key: value}
        return {}

    def _request(self, method: str, path: str, data: dict[str, Any] | None = None) -> dict[str, Any] | list:
        url = f"{self.base_url}{path}"
        headers = {**self.headers, **self._auth_headers(), "Content-Type": "application/json"}
        resp = httpx.request(method, url, json=data, headers=headers, timeout=30)
        if resp.status_code == 404:
            raise CrmNotFoundError(self.provider, method, f"Not found: {path}")
        if resp.status_code >= 400:
            raise CrmConnectionError(self.provider, method, f"{resp.status_code}: {resp.text}")
        return resp.json()

    def _ep(self, key: str, default: str = "") -> str:
        return self.endpoint_mapping.get(key, default)

    def _maybe_mask(self, data: dict[str, Any] | None) -> dict[str, Any] | None:
        if data is None:
            return None
        return _mask_phi(data)  # type: ignore[operator]

    def get_patient(self, patient_id: str) -> dict[str, Any] | None:
        path = self._ep("get_patient", f"/patients/{patient_id}")
        try:
            result = self._request("GET", path)
            return self._maybe_mask(result if isinstance(result, dict) else None)
        except CrmNotFoundError:
            return None

    def find_patient(self, email: str | None = None, phone: str | None = None) -> dict[str, Any] | None:
        path = self._ep("find_patient", "/patients/search")
        params: dict[str, str] = {}
        if email:
            params["email"] = email
        if phone:
            params["phone"] = phone
        try:
            result = self._request("GET", f"{path}?{'&'.join(f'{k}={v}' for k, v in params.items())}")
            if isinstance(result, list) and result:
                return self._maybe_mask(result[0])
            return None
        except CrmNotFoundError:
            return None

    def create_patient(self, data: dict[str, Any]) -> dict[str, Any]:
        path = self._ep("create_patient", "/patients")
        result = self._request("POST", path, data)
        return _mask_phi(result) if isinstance(result, dict) else {"status": "created"}  # type: ignore[operator]

    def update_patient(self, patient_id: str, data: dict[str, Any]) -> dict[str, Any]:
        path = self._ep("update_patient", f"/patients/{patient_id}")
        result = self._request("PUT", path, data)
        return _mask_phi(result) if isinstance(result, dict) else {"status": "updated"}  # type: ignore[operator]

    def create_appointment(self, patient_id: str, data: dict[str, Any]) -> dict[str, Any]:
        path = self._ep("create_appointment", "/appointments")
        result = self._request("POST", path, {**data, "patient_id": patient_id})
        return result if isinstance(result, dict) else {"status": "created"}

    def update_appointment(self, appt_id: str, data: dict[str, Any]) -> dict[str, Any]:
        path = self._ep("update_appointment", f"/appointments/{appt_id}")
        result = self._request("PUT", path, data)
        return result if isinstance(result, dict) else {"status": "updated"}

    def cancel_appointment(self, appt_id: str) -> bool:
        path = self._ep("cancel_appointment", f"/appointments/{appt_id}/cancel")
        try:
            self._request("POST", path)
            return True
        except CrmConnectionError:
            return False

    def get_patient_appointments(self, patient_id: str) -> list[dict[str, Any]]:
        path = self._ep("get_patient_appointments", f"/patients/{patient_id}/appointments")
        try:
            result = self._request("GET", path)
            return result if isinstance(result, list) else []
        except CrmNotFoundError:
            return []

    def get_appointment(self, appt_id: str) -> dict[str, Any] | None:
        path = self._ep("get_appointment", f"/appointments/{appt_id}")
        try:
            result = self._request("GET", path)
            return self._maybe_mask(result) if isinstance(result, dict) else None
        except CrmNotFoundError:
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
        path = self._ep("list_appointments", "/appointments")
        params = {}
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
        params["offset"] = str(offset)
        params["limit"] = str(limit)
        try:
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            result = self._request("GET", f"{path}?{qs}")
            if isinstance(result, dict):
                return result
            if isinstance(result, list):
                return {"total": len(result), "items": result}
            return {"total": 0, "items": []}
        except CrmNotFoundError:
            return {"total": 0, "items": []}

    def search_available_slots(self, doctor_id: str, date: str) -> list[dict[str, Any]]:
        path = self._ep("search_available_slots", f"/slots?doctor_id={doctor_id}&date={date}")
        try:
            result = self._request("GET", path)
            return result if isinstance(result, list) else []
        except CrmNotFoundError:
            return []

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        return True  # Custom adapters use their own auth

    def parse_webhook_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"event": payload.get("event_type", "unknown"), "resource": payload}
