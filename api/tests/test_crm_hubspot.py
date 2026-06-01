from __future__ import annotations

import hashlib
import hmac as hmac_lib
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.integrations.crm.exceptions import CrmConnectionError, CrmNotFoundError
from app.integrations.crm.hubspot import HubSpotAdapter


@pytest.fixture
def config() -> dict[str, Any]:
    return {
        "access_token": "test_access_token",
        "portal_id": "12345",
    }


@pytest.fixture
def adapter(config: dict[str, Any]) -> HubSpotAdapter:
    return HubSpotAdapter(config)


@pytest.fixture
def mock_httpx_request() -> MagicMock:
    with patch("app.integrations.crm.hubspot.httpx.request") as mock:
        yield mock


def _mock_response(status_code: int = 200, json_data: Any = None, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    resp.text = text
    return resp


class TestInit:
    def test_sets_config_values(self, config: dict[str, Any]):
        a = HubSpotAdapter(config)
        assert a.access_token == "test_access_token"
        assert a.portal_id == "12345"

    def test_default_portal_id(self):
        a = HubSpotAdapter({"access_token": "tok"})
        assert a.portal_id == ""

    def test_provider_meta(self):
        assert HubSpotAdapter.provider == "hubspot"
        assert HubSpotAdapter.phi_safe is False


class TestApiRequest:
    def test_success(self, adapter: HubSpotAdapter, mock_httpx_request: MagicMock):
        mock_httpx_request.return_value = _mock_response(json_data={"id": "1"})
        result = adapter._api_request("GET", "/crm/v3/contacts/1")
        assert result == {"id": "1"}

    def test_404_raises_not_found(self, adapter: HubSpotAdapter, mock_httpx_request: MagicMock):
        mock_httpx_request.return_value = _mock_response(status_code=404, text="not found")
        with pytest.raises(CrmNotFoundError):
            adapter._api_request("GET", "/crm/v3/contacts/999")

    def test_400_raises_connection_error(self, adapter: HubSpotAdapter, mock_httpx_request: MagicMock):
        mock_httpx_request.return_value = _mock_response(status_code=400, text="bad request")
        with pytest.raises(CrmConnectionError):
            adapter._api_request("POST", "/crm/v3/contacts")

    def test_passes_authorization_header(self, adapter: HubSpotAdapter, mock_httpx_request: MagicMock):
        mock_httpx_request.return_value = _mock_response(json_data={})
        adapter._api_request("GET", "/crm/v3/contacts")
        headers = mock_httpx_request.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer test_access_token"


class TestPhiRestrictions:
    def test_get_patient_raises(self, adapter: HubSpotAdapter):
        with pytest.raises(CrmConnectionError, match="PHI"):
            adapter.get_patient("1")

    def test_find_patient_raises(self, adapter: HubSpotAdapter):
        with pytest.raises(CrmConnectionError, match="PHI"):
            adapter.find_patient(email="a@b.com")

    def test_create_patient_raises(self, adapter: HubSpotAdapter):
        with pytest.raises(CrmConnectionError, match="PHI"):
            adapter.create_patient({"name": "test"})

    def test_update_patient_raises(self, adapter: HubSpotAdapter):
        with pytest.raises(CrmConnectionError, match="PHI"):
            adapter.update_patient("1", {"name": "test"})

    def test_update_appointment_raises(self, adapter: HubSpotAdapter):
        with pytest.raises(CrmConnectionError, match="Not implemented"):
            adapter.update_appointment("a1", {})

    def test_cancel_appointment_raises(self, adapter: HubSpotAdapter):
        with pytest.raises(CrmConnectionError, match="Not implemented"):
            adapter.cancel_appointment("a1")

    def test_get_patient_appointments_raises(self, adapter: HubSpotAdapter):
        with pytest.raises(CrmConnectionError, match="Not implemented"):
            adapter.get_patient_appointments("p1")


class TestCreateAppointment:
    def test_success(self, adapter: HubSpotAdapter, mock_httpx_request: MagicMock):
        mock_httpx_request.return_value = _mock_response(json_data={"engagement": {"id": 100}})
        result = adapter.create_appointment("42", {
            "provider_name": "Dr. Smith",
            "start_time": "2025-01-01T10:00",
            "end_time": "2025-01-01T10:30",
            "reason": "Checkup",
        })
        assert result["engagement"]["id"] == 100

    def test_sends_correct_body(self, adapter: HubSpotAdapter, mock_httpx_request: MagicMock):
        mock_httpx_request.return_value = _mock_response(json_data={"engagement": {"id": 1}})
        adapter.create_appointment("42", {
            "provider_name": "Dr. X",
            "start_time": "2025-01-01T10:00",
            "end_time": "2025-01-01T10:30",
            "reason": "Pain",
        })
        body = mock_httpx_request.call_args[1]["json"]
        assert body["engagement"]["type"] == "MEETING"
        assert body["associations"]["contactIds"] == [42]
        assert body["metadata"]["title"] == "Appointment with Dr. X"
        assert body["metadata"]["body"] == "Pain"

    def test_error_response(self, adapter: HubSpotAdapter, mock_httpx_request: MagicMock):
        mock_httpx_request.return_value = _mock_response(status_code=400, text="invalid")
        with pytest.raises(CrmConnectionError):
            adapter.create_appointment("42", {"provider_name": "Dr. X", "start_time": "T1", "end_time": "T2"})


class TestGetAppointment:
    def test_raises_not_implemented(self, adapter: HubSpotAdapter):
        with pytest.raises(CrmConnectionError, match="does not support appointment listing"):
            adapter.get_appointment("a1")


class TestListAppointments:
    def test_raises_not_implemented(self, adapter: HubSpotAdapter):
        with pytest.raises(CrmConnectionError, match="does not support appointment listing"):
            adapter.list_appointments("t1")


class TestSearchAvailableSlots:
    def test_returns_empty_list(self, adapter: HubSpotAdapter):
        result = adapter.search_available_slots("doc1", "2025-01-01")
        assert result == []


class TestVerifyWebhookSignature:
    def test_valid_signature(self, adapter: HubSpotAdapter):
        payload = b'{"subscriptionType": "contact.creation"}'
        key = "test-fernet-key-32-chars-len!"
        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.fernet_key = key
            expected = hmac_lib.new(key.encode(), payload, hashlib.sha256).hexdigest()
            assert adapter.verify_webhook_signature(payload, expected) is True

    def test_invalid_signature(self, adapter: HubSpotAdapter):
        payload = b'{"subscriptionType": "contact.creation"}'
        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.fernet_key = "test-fernet-key-32-chars-len!"
            assert adapter.verify_webhook_signature(payload, "bad_sig") is False


class TestParseWebhookEvent:
    def test_parses_contact_event(self, adapter: HubSpotAdapter):
        payload = {"subscriptionType": "contact.creation", "objectId": 12345}
        result = adapter.parse_webhook_event(payload)
        assert result["event"] == "contact.creation"
        assert result["resource"] == 12345

    def test_unknown_event(self, adapter: HubSpotAdapter):
        payload = {"objectId": {}}
        result = adapter.parse_webhook_event(payload)
        assert result["event"] == "unknown"
