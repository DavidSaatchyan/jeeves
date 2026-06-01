from __future__ import annotations

import hmac
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.integrations.crm.exceptions import CrmAuthError, CrmConnectionError, CrmNotFoundError, CrmRateLimitError
from app.integrations.crm.zoho import ZohoCRMAdapter


@pytest.fixture
def config() -> dict[str, Any]:
    return {
        "client_id": "test_client_id",
        "client_secret": "test_client_secret",
        "refresh_token": "test_refresh_token",
        "accounts_domain": "accounts.zoho.test",
        "api_domain": "api.zoho.test",
    }


@pytest.fixture
def adapter(config: dict[str, Any]) -> ZohoCRMAdapter:
    return ZohoCRMAdapter(config)


@pytest.fixture
def mock_httpx_post() -> MagicMock:
    with patch("app.integrations.crm.zoho.httpx.post") as mock:
        yield mock


@pytest.fixture
def mock_httpx_request() -> MagicMock:
    with patch("app.integrations.crm.zoho.httpx.request") as mock:
        yield mock


def _mock_response(status_code: int = 200, json_data: Any = None, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else {}
    resp.text = text
    return resp


class TestInit:
    def test_sets_config_values(self, config: dict[str, Any]):
        a = ZohoCRMAdapter(config)
        assert a.client_id == "test_client_id"
        assert a.client_secret == "test_client_secret"
        assert a.refresh_token == "test_refresh_token"
        assert a.accounts_domain == "accounts.zoho.test"
        assert a.api_domain == "api.zoho.test"

    def test_uses_default_domains(self):
        minimal = {"client_id": "x", "client_secret": "y", "refresh_token": "z"}
        a = ZohoCRMAdapter(minimal)
        assert a.accounts_domain == "accounts.zoho.com"
        assert a.api_domain == "www.zohoapis.com"

    def test_provider_meta(self):
        assert ZohoCRMAdapter.provider == "zoho"
        assert ZohoCRMAdapter.phi_safe is True


class TestRefreshAccessToken:
    def test_success(self, adapter: ZohoCRMAdapter, mock_httpx_post: MagicMock):
        mock_httpx_post.return_value = _mock_response(json_data={
            "access_token": "new_token_123",
            "expires_in_sec": 3600,
        })
        adapter._refresh_access_token()
        assert adapter._access_token == "new_token_123"
        assert adapter._token_expires_at > time.time()

    def test_failure_raises_auth_error(self, adapter: ZohoCRMAdapter, mock_httpx_post: MagicMock):
        mock_httpx_post.return_value = _mock_response(status_code=400, text="invalid_grant")
        with pytest.raises(CrmAuthError) as excinfo:
            adapter._refresh_access_token()
        assert "invalid_grant" in str(excinfo.value)

    def test_posts_correct_data(self, adapter: ZohoCRMAdapter, mock_httpx_post: MagicMock):
        mock_httpx_post.return_value = _mock_response(json_data={"access_token": "t", "expires_in_sec": 3600})
        adapter._refresh_access_token()
        call_kwargs = mock_httpx_post.call_args[1]
        assert call_kwargs["data"]["grant_type"] == "refresh_token"
        assert call_kwargs["data"]["refresh_token"] == "test_refresh_token"
        assert call_kwargs["data"]["client_id"] == "test_client_id"


class TestEnsureToken:
    def test_refreshes_when_expired(self, adapter: ZohoCRMAdapter):
        adapter._token_expires_at = time.time() - 10
        with patch.object(adapter, "_refresh_access_token") as mock_refresh:
            adapter._ensure_token()
            mock_refresh.assert_called_once()

    def test_skips_refresh_when_valid(self, adapter: ZohoCRMAdapter):
        adapter._token_expires_at = time.time() + 3600
        adapter._access_token = "valid_token"
        with patch.object(adapter, "_refresh_access_token") as mock_refresh:
            adapter._ensure_token()
            mock_refresh.assert_not_called()

    def test_refreshes_when_near_expiry(self, adapter: ZohoCRMAdapter):
        adapter._token_expires_at = time.time() + 30
        with patch.object(adapter, "_refresh_access_token") as mock_refresh:
            adapter._ensure_token()
            mock_refresh.assert_called_once()


class TestApiRequest:
    def test_success(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(json_data={"data": [{"id": "1"}]})
        result = adapter._api_request("GET", "/crm/v7/Contacts/1")
        assert result == [{"id": "1"}]

    def test_401_triggers_refresh(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "expired_tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.side_effect = [
            _mock_response(status_code=401, text="unauthorized"),
            _mock_response(json_data={"data": [{"id": "1"}]}),
        ]
        with patch.object(adapter, "_refresh_access_token") as mock_refresh:
            result = adapter._api_request("GET", "/crm/v7/Contacts/1")
            assert mock_refresh.called
            assert result == [{"id": "1"}]
            assert mock_httpx_request.call_count == 2

    def test_429_raises_rate_limit(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(status_code=429, text="rate limit")
        with pytest.raises(CrmRateLimitError):
            adapter._api_request("POST", "/crm/v7/Contacts")

    def test_404_raises_not_found(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(status_code=404, text="not found")
        with pytest.raises(CrmNotFoundError):
            adapter._api_request("GET", "/crm/v7/Contacts/999")

    def test_400_raises_connection_error(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(status_code=400, text="bad request")
        with pytest.raises(CrmConnectionError):
            adapter._api_request("POST", "/crm/v7/Contacts")

    def test_passes_authorization_header(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "mytoken"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(json_data={"data": []})
        adapter._api_request("GET", "/crm/v7/Contacts")
        headers = mock_httpx_request.call_args[1]["headers"]
        assert headers["Authorization"] == "Zoho-oauthtoken mytoken"


class TestGetPatient:
    def test_success(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(json_data={"data": [{"id": "42", "First_Name": "John"}]})
        result = adapter.get_patient("42")
        assert result == [{"id": "42", "First_Name": "John"}]

    def test_not_found_returns_none(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(status_code=404, text="not found")
        result = adapter.get_patient("999")
        assert result is None


class TestFindPatient:
    def test_by_email(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(json_data={"data": [{"id": "1", "Email": "a@b.com"}]})
        result = adapter.find_patient(email="a@b.com")
        assert result == {"id": "1", "Email": "a@b.com"}

    def test_by_phone(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(json_data={"data": [{"id": "2", "Phone": "123"}]})
        result = adapter.find_patient(phone="123")
        assert result == {"id": "2", "Phone": "123"}

    def test_no_criteria_returns_none(self, adapter: ZohoCRMAdapter):
        result = adapter.find_patient()
        assert result is None

    def test_no_match_returns_none(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(status_code=404, text="not found")
        result = adapter.find_patient(email="missing@test.com")
        assert result is None

    def test_empty_result_list_returns_none(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(json_data={"data": []})
        result = adapter.find_patient(email="nobody@test.com")
        assert result is None


class TestCreatePatient:
    def test_success(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(json_data={"data": [{"id": "100", "First_Name": "Jane"}]})
        result = adapter.create_patient({"first_name": "Jane", "last_name": "Doe", "email": "j@d.com"})
        assert result["id"] == "100"

    def test_sends_mapped_fields(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(json_data={"data": [{"id": "1"}]})
        adapter.create_patient({"first_name": "A", "last_name": "B", "email": "c@d.com", "phone": "555", "date_of_birth": "1990-01-01", "gender": "F"})
        body = mock_httpx_request.call_args[1]["json"]
        contact = body["data"][0]
        assert contact["First_Name"] == "A"
        assert contact["Last_Name"] == "B"
        assert contact["Email"] == "c@d.com"
        assert contact["Phone"] == "555"
        assert contact["Date_of_Birth"] == "1990-01-01"
        assert contact["Gender"] == "F"

    def test_empty_response_fallback(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(json_data={"data": []})
        result = adapter.create_patient({"first_name": "X"})
        assert result["status"] == "created"


class TestUpdatePatient:
    def test_success(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(json_data={"data": [{"id": "1", "First_Name": "Updated"}]})
        result = adapter.update_patient("1", {"first_name": "Updated"})
        assert result == [{"id": "1", "First_Name": "Updated"}]


class TestCreateAppointment:
    def test_success(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(json_data={"data": [{"id": "appt1"}]})
        result = adapter.create_appointment("p1", {"provider_name": "Dr. Smith", "start_time": "2025-01-01T10:00", "end_time": "2025-01-01T10:30"})
        assert result["id"] == "appt1"

    def test_sends_body(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(json_data={"data": [{"id": "a1"}]})
        adapter.create_appointment("p1", {"provider_name": "Dr. X", "start_time": "T1", "end_time": "T2", "reason": "Checkup"})
        body = mock_httpx_request.call_args[1]["json"]
        assert body["data"][0]["Patient_ID"] == "p1"
        assert body["data"][0]["Status"] == "Scheduled"


class TestGetAppointment:
    def test_success(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(json_data={"data": [{"id": "a1", "Status": "Scheduled"}]})
        result = adapter.get_appointment("a1")
        assert result == {"id": "a1", "Status": "Scheduled"}

    def test_not_found_returns_none(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(status_code=404, text="not found")
        result = adapter.get_appointment("missing")
        assert result is None

    def test_non_list_result_returns_as_is(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(json_data={"id": "a2", "Status": "Completed"})
        result = adapter.get_appointment("a2")
        assert result == {"id": "a2", "Status": "Completed"}


class TestListAppointments:
    def test_success(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(json_data={"data": [{"id": "a1"}, {"id": "a2"}]})
        result = adapter.list_appointments("t1")
        assert result["total"] == 2

    def test_empty(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(json_data={"data": []})
        result = adapter.list_appointments("t1")
        assert result["total"] == 0
        assert result["items"] == []

    def test_not_found_returns_empty(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(status_code=404, text="not found")
        result = adapter.list_appointments("t1")
        assert result["total"] == 0
        assert result["items"] == []

    def test_filters_by_status(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(json_data={"data": [{"id": "a1"}]})
        adapter.list_appointments("t1", status="Scheduled")
        called_path = mock_httpx_request.call_args[0][1]
        assert "Status:equals:Scheduled" in called_path

    def test_filters_by_date_range(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(json_data={"data": [{"id": "a1"}]})
        adapter.list_appointments("t1", date_from="2026-01-01", date_to="2026-01-31")
        called_path = mock_httpx_request.call_args[0][1]
        assert "Start_Time:greater_or_equal:2026-01-01" in called_path
        assert "Start_Time:less_or_equal:2026-01-31" in called_path

    def test_respects_offset_and_limit(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(json_data={"data": [{"id": "a1"}, {"id": "a2"}, {"id": "a3"}]})
        result = adapter.list_appointments("t1", offset=1, limit=1)
        assert len(result["items"]) == 1
        assert result["items"][0]["id"] == "a2"


class TestCancelAppointment:
    def test_success_returns_true(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(json_data={"data": [{"id": "a1"}]})
        assert adapter.cancel_appointment("a1") is True

    def test_failure_returns_false(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(status_code=400, text="error")
        assert adapter.cancel_appointment("a1") is False


class TestGetPatientAppointments:
    def test_success(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(json_data={"data": [{"id": "a1"}, {"id": "a2"}]})
        result = adapter.get_patient_appointments("p1")
        assert len(result) == 2

    def test_not_found_returns_empty(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(status_code=404, text="not found")
        result = adapter.get_patient_appointments("p1")
        assert result == []

    def test_non_list_result_returns_empty(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(json_data={"data": {}})
        result = adapter.get_patient_appointments("p1")
        assert result == []


class TestSearchAvailableSlots:
    def test_success(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(json_data={"data": [{"slot": "10:00"}, {"slot": "11:00"}]})
        result = adapter.search_available_slots("doc1", "2025-01-01")
        assert len(result) == 2

    def test_not_found_returns_empty(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(status_code=404, text="not found")
        result = adapter.search_available_slots("doc1", "2025-01-01")
        assert result == []

    def test_non_list_result_returns_empty(self, adapter: ZohoCRMAdapter, mock_httpx_request: MagicMock):
        adapter._access_token = "tok"
        adapter._token_expires_at = time.time() + 3600
        mock_httpx_request.return_value = _mock_response(json_data={"data": {}})
        result = adapter.search_available_slots("doc1", "2025-01-01")
        assert result == []


class TestVerifyWebhookSignature:
    def test_valid_signature(self, adapter: ZohoCRMAdapter):
        payload = b'{"event": "test"}'
        key = "test-fernet-key-32-chars-len!"
        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.fernet_key = key
            expected = hmac.new(key.encode(), payload, "sha256").hexdigest()
            assert adapter.verify_webhook_signature(payload, expected) is True

    def test_invalid_signature(self, adapter: ZohoCRMAdapter):
        payload = b'{"event": "test"}'
        key = "test-fernet-key-32-chars-len!"
        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value.fernet_key = key
            assert adapter.verify_webhook_signature(payload, "bad_signature_here") is False


class TestParseWebhookEvent:
    def test_parses_event(self, adapter: ZohoCRMAdapter):
        payload = {"event": {"type": "contact.created", "resource": {"id": "123"}}}
        result = adapter.parse_webhook_event(payload)
        assert result["event"] == "contact.created"
        assert result["resource"] == {"id": "123"}

    def test_unknown_event(self, adapter: ZohoCRMAdapter):
        payload = {"not_event": {}}
        result = adapter.parse_webhook_event(payload)
        assert result["event"] == "unknown"
        assert result["resource"] == {}
