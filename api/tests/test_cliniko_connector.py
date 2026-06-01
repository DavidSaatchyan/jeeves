"""Unit tests for Cliniko CRM connector."""
from __future__ import annotations

from unittest.mock import ANY, MagicMock, patch

import httpx
import pytest

from app.integrations.exceptions import ConnectorAuthError, ConnectorError, ConnectorNotFoundError, ConnectorRateLimitError
from app.integrations.cliniko import ClinikoConnector, _map_patient_to_cliniko


def _make_connector(**overrides: str) -> ClinikoConnector:
    config = {"api_key": "cliniko-key", "shard": "au1", "user_agent": "TestApp (test@test.com)"}
    config.update(overrides)
    return ClinikoConnector(config)


# ── Init ─────────────────────────────────────────────────────────────────────────────────


class TestClinikoConnectorInit:
    def test_constructs_from_config(self):
        c = _make_connector()
        assert c.api_key == "cliniko-key"
        assert c.shard == "au1"
        assert c.user_agent == "TestApp (test@test.com)"
        assert "au1" in c.base_url

    def test_default_shard(self):
        c = ClinikoConnector({"api_key": "k"})
        assert c.shard == "au1"

    def test_custom_shard(self):
        c = _make_connector(shard="eu1")
        assert "eu1" in c.base_url

    def test_provider_and_phi_attrs(self):
        c = _make_connector()
        assert c.provider == "cliniko"
        assert c.phi_safe is True


# ── Auth ─────────────────────────────────────────────────────────────────────────────────


class TestClinikoAuth:
    def test_auth_header_is_basic(self):
        c = _make_connector(api_key="test:key")
        hdr = c._auth_header()
        assert hdr.startswith("Basic ")

    def test_headers_include_user_agent(self):
        c = _make_connector()
        hdrs = c._headers()
        assert hdrs["Authorization"].startswith("Basic ")
        assert hdrs["Accept"] == "application/json"
        assert hdrs["User-Agent"] == "TestApp (test@test.com)"


# ── _request ─────────────────────────────────────────────────────────────────────────────


class TestClinikoRequest:
    def test_get_returns_json(self):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": 1, "first_name": "Jane"}

        with patch("app.integrations.cliniko.httpx.request", return_value=mock_resp) as mock_req:
            c = _make_connector()
            result = c._request("GET", "/patients/1")
        assert result == {"id": 1, "first_name": "Jane"}
        mock_req.assert_called_once_with(
            "GET", "https://api.au1.cliniko.com/v1/patients/1",
            headers=ANY, timeout=30,
        )

    def test_401_raises_auth_error(self):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 401
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError("401", request=MagicMock(), response=mock_resp)

        with patch("app.integrations.cliniko.httpx.request", return_value=mock_resp):
            c = _make_connector()
            with pytest.raises(ConnectorAuthError, match="Invalid API key"):
                c._request("GET", "/patients")

    def test_404_raises_not_found(self):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 404
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError("404", request=MagicMock(), response=mock_resp)

        with patch("app.integrations.cliniko.httpx.request", return_value=mock_resp):
            c = _make_connector()
            with pytest.raises(ConnectorNotFoundError):
                c._request("GET", "/patients/nonexistent")

    def test_429_raises_rate_limit(self):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 429
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError("429", request=MagicMock(), response=mock_resp)

        with patch("app.integrations.cliniko.httpx.request", return_value=mock_resp):
            c = _make_connector()
            with pytest.raises(ConnectorRateLimitError):
                c._request("GET", "/patients")

    def test_500_raises_generic_error(self):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError("500", request=MagicMock(), response=mock_resp)
        mock_resp.text = "Server error"

        with patch("app.integrations.cliniko.httpx.request", return_value=mock_resp):
            c = _make_connector()
            with pytest.raises(ConnectorError, match="HTTP 500"):
                c._request("GET", "/patients")

    def test_network_error(self):
        with patch("app.integrations.cliniko.httpx.request", side_effect=httpx.RequestError("timeout")):
            c = _make_connector()
            with pytest.raises(ConnectorError, match="timeout"):
                c._request("GET", "/patients")


# ── Patients ─────────────────────────────────────────────────────────────────────────────


class TestClinikoPatients:
    def test_get_patient_returns_dict(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={"id": 1, "first_name": "Jane"}) as mock:
            result = c.get_patient("1")
        assert result == {"id": 1, "first_name": "Jane"}
        mock.assert_called_once_with("GET", "/patients/1")

    def test_get_patient_returns_none_on_404(self):
        c = _make_connector()
        with patch.object(c, "_request", side_effect=ConnectorNotFoundError("cliniko", "GET", "")):
            result = c.get_patient("1")
        assert result is None

    def test_find_patient_by_email(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={"patients": [{"id": 1, "email": "a@b.com"}]}) as mock:
            result = c.find_patient(email="a@b.com")
        assert result == {"id": 1, "email": "a@b.com"}
        assert "email:=" in str(mock.call_args)

    def test_find_patient_by_phone(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={"patients": [{"id": 1}]}) as mock:
            result = c.find_patient(phone="+123")
        assert result == {"id": 1}
        assert "mobile:=" in str(mock.call_args)

    def test_find_patient_no_params_returns_none(self):
        c = _make_connector()
        result = c.find_patient()
        assert result is None

    def test_create_patient_maps_fields(self):
        c = _make_connector()
        data = {"first_name": "Bob", "last_name": "Smith", "email": "b@b.com", "phone": "+456"}
        with patch.object(c, "_request", return_value={"id": 99}) as mock:
            c.create_patient(data)
        called_json = mock.call_args[1]["json"]
        assert called_json["first_name"] == "Bob"
        assert called_json["mobile"] == "+456"
        assert "phone" not in called_json

    def test_update_patient(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={"id": 1}) as mock:
            c.update_patient("1", {"first_name": "Rob"})
        called_json = mock.call_args[1]["json"]
        assert called_json["first_name"] == "Rob"


# ── Appointments ─────────────────────────────────────────────────────────────────────────


class TestClinikoAppointments:
    def test_create_appointment(self):
        c = _make_connector()
        data = {"start_time": "2026-06-01T10:00:00Z", "end_time": "2026-06-01T10:30:00Z", "reason": "Checkup"}
        with patch.object(c, "_request", return_value={"id": "a1"}) as mock:
            result = c.create_appointment("p1", data)
        assert result["id"] == "a1"
        called = mock.call_args[1]["json"]
        assert called["patient_id"] == "/v1/patients/p1"
        assert called["starts_at"] == "2026-06-01T10:00:00Z"
        assert called["notes"] == "Checkup"

    def test_cancel_appointment_sets_cancelled_at(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value=None) as mock:
            result = c.cancel_appointment("a1")
        assert result is True
        called = mock.call_args[1]["json"]
        assert "cancelled_at" in called

    def test_cancel_appointment_returns_false_on_error(self):
        c = _make_connector()
        with patch.object(c, "_request", side_effect=ConnectorError("cliniko", "PUT", "fail")):
            assert c.cancel_appointment("a1") is False

    def test_get_appointment_returns_dict(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={"id": "a1"}):
            result = c.get_appointment("a1")
        assert result == {"id": "a1"}

    def test_get_appointment_returns_none_on_404(self):
        c = _make_connector()
        with patch.object(c, "_request", side_effect=ConnectorNotFoundError("cliniko", "GET", "")):
            result = c.get_appointment("a1")
        assert result is None

    def test_list_appointments_passes_params(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={"individual_appointments": []}) as mock:
            c.list_appointments("tid", date_from="2026-06-01", date_to="2026-06-30", limit=25)
        assert "starts_at:>=" in str(mock.call_args)
        assert "per_page" in str(mock.call_args)

    def test_get_patient_appointments(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={"individual_appointments": [{"id": "a1"}]}):
            result = c.get_patient_appointments("p1")
        assert result == [{"id": "a1"}]

    def test_get_patient_appointments_empty(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={}):
            result = c.get_patient_appointments("p1")
        assert result == []


# ── Slots ────────────────────────────────────────────────────────────────────────────────


class TestClinikoSlots:
    def test_search_available_slots(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={"available_times": [{"start": "09:00", "end": "09:30"}]}) as mock:
            result = c.search_available_slots("dr1", "2026-06-01")
        assert len(result) == 1
        assert result[0]["start"] == "09:00"
        assert "practitioner_id:=" in str(mock.call_args)

    def test_search_available_slots_empty(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={}):
            result = c.search_available_slots("dr1", "2026-06-01")
        assert result == []


# ── Connection Test ──────────────────────────────────────────────────────────────────────


class TestClinikoConnectionTest:
    def test_test_connection_success(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={"practitioners": []}):
            assert c.test_connection() is True

    def test_test_connection_failure(self):
        c = _make_connector()
        with patch.object(c, "_request", side_effect=ConnectorError("cliniko", "GET", "fail")):
            assert c.test_connection() is False


# ── Webhooks ─────────────────────────────────────────────────────────────────────────────


class TestClinikoWebhooks:
    def test_verify_signature_always_true(self):
        c = _make_connector()
        assert c.verify_webhook_signature(b"{}", "") is True
        assert c.verify_webhook_signature(b"{}", "any") is True

    def test_parse_webhook_event(self):
        c = _make_connector()
        payload = {"event": "appointment.created", "data": {"id": "a1"}}
        result = c.parse_webhook_event(payload)
        assert result["event"] == "appointment.created"
        assert result["resource"] == {"id": "a1"}

    def test_parse_webhook_event_unknown(self):
        c = _make_connector()
        result = c.parse_webhook_event({"foo": "bar"})
        assert result["event"] == "unknown"


# ── Practitioners ────────────────────────────────────────────────────────────────────────


class TestClinikoPractitioners:
    def test_get_practitioners_returns_list(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={"practitioners": [{"id": 1}]}):
            result = c.get_practitioners()
        assert result == [{"id": 1}]

    def test_get_practitioners_empty(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={}):
            result = c.get_practitioners()
        assert result == []

    def test_get_practitioner_by_id(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={"id": "dr1"}) as mock:
            result = c.get_practitioner_by_id("dr1")
        assert result == {"id": "dr1"}
        mock.assert_called_once_with("GET", "/practitioners/dr1")

    def test_get_practitioner_by_id_not_found(self):
        c = _make_connector()
        with patch.object(c, "_request", side_effect=ConnectorNotFoundError("cliniko", "GET", "")):
            result = c.get_practitioner_by_id("missing")
        assert result is None


# ── Appointment Types ───────────────────────────────────────────────────────────────────


class TestClinikoAppointmentTypes:
    def test_get_appointment_types_returns_list(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={"appointment_types": [{"id": 1}]}):
            result = c.get_appointment_types()
        assert result == [{"id": 1}]

    def test_get_appointment_types_empty(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={}):
            result = c.get_appointment_types()
        assert result == []

    def test_get_appointment_type_by_id(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={"id": "t1"}) as mock:
            result = c.get_appointment_type_by_id("t1")
        assert result == {"id": "t1"}
        mock.assert_called_once_with("GET", "/appointment_types/t1")

    def test_get_appointment_type_by_id_not_found(self):
        c = _make_connector()
        with patch.object(c, "_request", side_effect=ConnectorNotFoundError("cliniko", "GET", "")):
            result = c.get_appointment_type_by_id("missing")
        assert result is None


# ── Appointment creation with types ──────────────────────────────────────────────────────


class TestClinikoAppointmentWithTypes:
    def test_create_appointment_with_appointment_type(self):
        c = _make_connector()
        data = {"start_time": "10:00", "end_time": "10:30", "appointment_type_id": "t1"}
        with patch.object(c, "_request", return_value={"id": "a1"}) as mock:
            c.create_appointment("p1", data)
        called = mock.call_args[1]["json"]
        assert called["appointment_type_id"] == "/v1/appointment_types/t1"

    def test_update_appointment_with_appointment_type(self):
        c = _make_connector()
        data = {"start_time": "10:00", "appointment_type_id": "t2"}
        with patch.object(c, "_request", return_value={"id": "a1"}) as mock:
            c.update_appointment("a1", data)
        called = mock.call_args[1]["json"]
        assert called["appointment_type_id"] == "/v1/appointment_types/t2"


# ── Patient mapping ──────────────────────────────────────────────────────────────────────


class TestMapPatientToCliniko:
    def test_maps_phone_to_mobile(self):
        result = _map_patient_to_cliniko({"phone": "+123", "first_name": "A"})
        assert result["mobile"] == "+123"
        assert "phone" not in result

    def test_maps_all_fields(self):
        data = {"first_name": "A", "last_name": "B", "email": "a@b.com", "phone": "+1",
                "date_of_birth": "1990-01-01", "gender": "male", "notes": "test"}
        result = _map_patient_to_cliniko(data)
        assert result["first_name"] == "A"
        assert result["last_name"] == "B"
        assert result["email"] == "a@b.com"
        assert result["mobile"] == "+1"
        assert result["date_of_birth"] == "1990-01-01"
        assert result["gender"] == "male"
        assert result["notes"] == "test"

    def test_empty_data(self):
        result = _map_patient_to_cliniko({})
        assert result == {}
