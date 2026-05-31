from __future__ import annotations

import time
from typing import Any

import httpx

from .base import AbstractCrmConnector
from .exceptions import CrmAuthError, CrmConnectionError, CrmNotFoundError, CrmRateLimitError


class ZohoCRMAdapter(AbstractCrmConnector):
    """Zoho CRM adapter — BAA available, PHI-safe.

    Uses OAuth 2.0 with refresh_token for authentication.
    API v7 (Contacts, Appointments__s custom module).
    """

    provider = "zoho"
    phi_safe = True

    def __init__(self, config: dict[str, Any]) -> None:
        self.client_id: str = config["client_id"]
        self.client_secret: str = config["client_secret"]
        self.refresh_token: str = config["refresh_token"]
        self.accounts_domain: str = config.get("accounts_domain", "accounts.zoho.com")
        self.api_domain: str = config.get("api_domain", "www.zohoapis.com")
        self._access_token: str = ""
        self._token_expires_at: float = 0

    # ── OAuth ───────────────────────────────────────────────────

    def _refresh_access_token(self) -> None:
        resp = httpx.post(
            f"https://{self.accounts_domain}/oauth/v2/token",
            data={
                "refresh_token": self.refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        if resp.status_code != 200:
            raise CrmAuthError(self.provider, "refresh_token", resp.text)
        data = resp.json()
        self._access_token = data["access_token"]
        self._token_expires_at = time.time() + int(data.get("expires_in_sec", 3600))

    def _ensure_token(self) -> None:
        if time.time() >= self._token_expires_at - 60:
            self._refresh_access_token()

    # ── HTTP ─────────────────────────────────────────────────────

    def _api_request(
        self, method: str, path: str, data: dict[str, Any] | None = None
    ) -> dict[str, Any] | list[dict[str, Any]]:
        self._ensure_token()
        url = f"https://{self.api_domain}{path}"
        headers = {
            "Authorization": f"Zoho-oauthtoken {self._access_token}",
            "Content-Type": "application/json",
        }
        resp = httpx.request(method, url, json=data, headers=headers, timeout=30)

        if resp.status_code == 401:
            self._refresh_access_token()
            headers["Authorization"] = f"Zoho-oauthtoken {self._access_token}"
            resp = httpx.request(method, url, json=data, headers=headers, timeout=30)

        if resp.status_code == 429:
            raise CrmRateLimitError(self.provider, method, "Rate limit exceeded")

        if resp.status_code == 404:
            raise CrmNotFoundError(self.provider, method, f"Resource not found: {path}")

        if resp.status_code >= 400:
            raise CrmConnectionError(self.provider, method, f"{resp.status_code}: {resp.text}")

        result = resp.json()
        return result.get("data", result)

    # ── Patients ─────────────────────────────────────────────────

    def get_patient(self, patient_id: str) -> dict[str, Any] | None:
        try:
            return self._api_request("GET", f"/crm/v7/Contacts/{patient_id}")  # type: ignore[return-value]
        except CrmNotFoundError:
            return None

    def find_patient(
        self, email: str | None = None, phone: str | None = None
    ) -> dict[str, Any] | None:
        criteria: list[str] = []
        if email:
            criteria.append(f"Email:equals:{email}")
        if phone:
            criteria.append(f"Phone:equals:{phone}")
        if not criteria:
            return None
        path = f"/crm/v7/Contacts/search?criteria=({','.join(criteria)})"
        try:
            result = self._api_request("GET", path)
            if isinstance(result, list) and result:
                return result[0]
            return None
        except CrmNotFoundError:
            return None

    def create_patient(self, data: dict[str, Any]) -> dict[str, Any]:
        body = {
            "data": [
                {
                    "First_Name": data.get("first_name", ""),
                    "Last_Name": data.get("last_name", ""),
                    "Email": data.get("email", ""),
                    "Phone": data.get("phone", ""),
                    "Date_of_Birth": data.get("date_of_birth", ""),
                    "Gender": data.get("gender", ""),
                }
            ]
        }
        result = self._api_request("POST", "/crm/v7/Contacts", body)
        if isinstance(result, list) and result:
            return result[0]
        return {"id": "", "status": "created"}

    def update_patient(self, patient_id: str, data: dict[str, Any]) -> dict[str, Any]:
        body = {"data": [data]}
        return self._api_request("PUT", f"/crm/v7/Contacts/{patient_id}", body)  # type: ignore[return-value]

    # ── Appointments ─────────────────────────────────────────────

    def create_appointment(self, patient_id: str, data: dict[str, Any]) -> dict[str, Any]:
        body = {
            "data": [
                {
                    "Patient_ID": patient_id,
                    "Provider_Name": data.get("provider_name", ""),
                    "Start_Time": data.get("start_time", ""),
                    "End_Time": data.get("end_time", ""),
                    "Reason": data.get("reason", ""),
                    "Status": data.get("status", "Scheduled"),
                }
            ]
        }
        result = self._api_request("POST", "/crm/v7/Appointments__s", body)
        if isinstance(result, list) and result:
            return result[0]
        return {"id": "", "status": "created"}

    def update_appointment(self, appt_id: str, data: dict[str, Any]) -> dict[str, Any]:
        body = {"data": [data]}
        return self._api_request("PUT", f"/crm/v7/Appointments__s/{appt_id}", body)  # type: ignore[return-value]

    def cancel_appointment(self, appt_id: str) -> bool:
        try:
            self._api_request("PUT", f"/crm/v7/Appointments__s/{appt_id}", {"data": [{"Status": "Cancelled"}]})
            return True
        except CrmConnectionError:
            return False

    def get_patient_appointments(self, patient_id: str) -> list[dict[str, Any]]:
        try:
            result = self._api_request("GET", f"/crm/v7/Appointments__s/search?criteria=(Patient_ID:equals:{patient_id})")
            if isinstance(result, list):
                return result
            return []
        except CrmNotFoundError:
            return []

    # ── Slots ────────────────────────────────────────────────────

    def search_available_slots(self, doctor_id: str, date: str) -> list[dict[str, Any]]:
        try:
            result = self._api_request(
                "GET",
                f"/crm/v7/Doctors__s/{doctor_id}/Slots__s/search?criteria=(Date:equals:{date})",
            )
            if isinstance(result, list):
                return result
            return []
        except CrmNotFoundError:
            return []

    # ── Webhooks ─────────────────────────────────────────────────

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        import hmac
        from ...config import get_settings
        expected = hmac.new(
            get_settings().fernet_key.encode(), payload, "sha256"
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def parse_webhook_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "event": payload.get("event", {}).get("type", "unknown"),
            "resource": payload.get("event", {}).get("resource", {}),
        }
