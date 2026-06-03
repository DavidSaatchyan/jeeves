"""Unit tests for Pabau CRM connector."""
from __future__ import annotations

from unittest.mock import ANY, MagicMock, patch

import httpx
import pytest

from app.integrations.exceptions import ConnectorAuthError, ConnectorError, ConnectorNotFoundError, ConnectorRateLimitError
from app.integrations.pabau import PabauConnector


def _make_connector(**overrides: str) -> PabauConnector:
    config = {"api_key": "test-key", "company_id": "42", "webhook_secret": "whsec_test"}
    config.update(overrides)
    return PabauConnector(config)


# ── Init ─────────────────────────────────────────────────────────────────────────────────


class TestPabauConnectorInit:
    def test_constructs_from_config(self):
        c = _make_connector()
        assert c.api_key == "test-key"
        assert c.company_id == "42"
        assert c.webhook_secret == "whsec_test"
        assert c.base_url == "https://api.oauth.pabau.com"

    def test_custom_base_url(self):
        c = _make_connector(base_url="https://eu.pabau.com/")
        assert c.base_url == "https://eu.pabau.com"

    def test_missing_key_defaults_to_empty(self):
        c = PabauConnector({})
        assert c.api_key == ""
        assert c.company_id == ""

    def test_provider_and_phi_attrs(self):
        c = _make_connector()
        assert c.provider == "pabau"
        assert c.phi_safe is True


# ── _request ─────────────────────────────────────────────────────────────────────────────


class TestPabauRequest:
    def test_get_returns_json(self):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": 1, "name": "John"}

        with patch("app.integrations.pabau.httpx.request", return_value=mock_resp) as mock_req:
            c = _make_connector()
            result = c._request("GET", "/patients/1")

        assert result == {"id": 1, "name": "John"}
        mock_req.assert_called_once_with(
            "GET", "https://api.oauth.pabau.com/test-key/patients/1",
            headers=ANY, timeout=30,
        )

    def test_sends_auth_headers(self):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}

        with patch("app.integrations.pabau.httpx.request", return_value=mock_resp) as mock_req:
            c = _make_connector()
            c._request("GET", "/test")

        headers = mock_req.call_args[1]["headers"]
        assert "X-API-Key" not in headers
        assert headers["X-Company-Id"] == "42"
        assert headers["Content-Type"] == "application/json"
        assert headers["Accept"] == "application/json"

    def test_post_sends_json_body(self):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"id": "new-1"}

        with patch("app.integrations.pabau.httpx.request", return_value=mock_resp) as mock_req:
            c = _make_connector()
            result = c._request("POST", "/patients", json={"name": "Jane"})

        assert result == {"id": "new-1"}
        assert mock_req.call_args[1]["json"] == {"name": "Jane"}

    def test_204_returns_none(self):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 204

        with patch("app.integrations.pabau.httpx.request", return_value=mock_resp):
            c = _make_connector()
            result = c._request("DELETE", "/appointments/1")
        assert result is None

    def test_401_raises_auth_error(self):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 401
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError("401", request=MagicMock(), response=mock_resp)

        with patch("app.integrations.pabau.httpx.request", return_value=mock_resp):
            c = _make_connector()
            with pytest.raises(ConnectorAuthError, match="Invalid API key"):
                c._request("GET", "/patients")

    def test_404_raises_not_found_error(self):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 404
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError("404", request=MagicMock(), response=mock_resp)

        with patch("app.integrations.pabau.httpx.request", return_value=mock_resp):
            c = _make_connector()
            with pytest.raises(ConnectorNotFoundError, match="Resource not found"):
                c._request("GET", "/patients/nonexistent")

    def test_429_raises_rate_limit_error(self):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 429
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError("429", request=MagicMock(), response=mock_resp)

        with patch("app.integrations.pabau.httpx.request", return_value=mock_resp):
            c = _make_connector()
            with pytest.raises(ConnectorRateLimitError, match="Rate limited"):
                c._request("GET", "/patients")

    def test_500_raises_generic_connector_error(self):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError("500", request=MagicMock(), response=mock_resp)
        mock_resp.text = "Internal error"

        with patch("app.integrations.pabau.httpx.request", return_value=mock_resp):
            c = _make_connector()
            with pytest.raises(ConnectorError, match="HTTP 500"):
                c._request("GET", "/patients")

    def test_network_error_raises_connector_error(self):
        with patch("app.integrations.pabau.httpx.request", side_effect=httpx.RequestError("connection failed")):
            c = _make_connector()
            with pytest.raises(ConnectorError, match="connection failed"):
                c._request("GET", "/patients")


# ── Practitioners & Services ──────────────────────────────────────────────────────────────


class TestPabauPractitioners:
    def test_get_practitioners_returns_list(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={"items": [{"id": "s1", "name": "Dr A"}]}) as mock:
            result = c.get_practitioners()
        assert result == [{"id": "s1", "name": "Dr A"}]
        mock.assert_called_once_with("GET", "/staff", params={"limit": 100})

    def test_get_practitioners_extracts_data(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={"data": [{"id": "s2"}]}):
            result = c.get_practitioners()
        assert result == [{"id": "s2"}]

    def test_get_practitioners_returns_plain_list(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value=[{"id": "s3"}]):
            result = c.get_practitioners()
        assert result == [{"id": "s3"}]

    def test_get_practitioners_empty(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={}):
            result = c.get_practitioners()
        assert result == []

    def test_get_services_returns_list(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={"items": [{"id": "svc1", "name": "Consultation"}]}) as mock:
            result = c.get_services()
        assert result == [{"id": "svc1", "name": "Consultation"}]
        mock.assert_called_once_with("GET", "/services", params={"limit": 100})

    def test_get_services_extracts_data(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={"data": [{"id": "svc2"}]}):
            result = c.get_services()
        assert result == [{"id": "svc2"}]

    def test_get_services_returns_plain_list(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value=[{"id": "svc3"}]):
            result = c.get_services()
        assert result == [{"id": "svc3"}]

    def test_get_services_empty(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={}):
            result = c.get_services()
        assert result == []


# ── Patients ─────────────────────────────────────────────────────────────────────────────


class TestPabauPatients:
    def test_get_patient_returns_dict(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={"id": "p1", "name": "Alice"}) as mock:
            result = c.get_patient("p1")
        assert result == {"id": "p1", "name": "Alice"}
        mock.assert_called_once_with("GET", "/patients/p1")

    def test_get_patient_returns_none_on_404(self):
        c = _make_connector()
        with patch.object(c, "_request", side_effect=ConnectorNotFoundError("pabau", "GET", "not found")):
            result = c.get_patient("p1")
        assert result is None

    def test_find_patient_by_email(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value=[{"id": "p1", "email": "a@b.com"}]) as mock:
            result = c.find_patient(email="a@b.com")
        assert result == {"id": "p1", "email": "a@b.com"}
        mock.assert_called_once_with("GET", "/patients", params={"email": "a@b.com", "limit": "1"})

    def test_find_patient_by_phone(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value=[{"id": "p1", "phone": "+123"}]) as mock:
            result = c.find_patient(phone="+123")
        assert result == {"id": "p1", "phone": "+123"}
        mock.assert_called_once_with("GET", "/patients", params={"phone": "+123", "limit": "1"})

    def test_find_patient_by_both(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value=[{"id": "p1"}]) as mock:
            result = c.find_patient(email="a@b.com", phone="+123")
        assert result == {"id": "p1"}
        mock.assert_called_once_with("GET", "/patients", params={"email": "a@b.com", "phone": "+123", "limit": "1"})

    def test_find_patient_no_params_returns_none(self):
        c = _make_connector()
        result = c.find_patient()
        assert result is None

    def test_find_patient_empty_results_returns_none(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value=[]):
            result = c.find_patient(email="x@y.com")
        assert result is None

    def test_find_patient_dict_response_with_items(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={"items": [{"id": "p1"}]}):
            result = c.find_patient(email="a@b.com")
        assert result == {"id": "p1"}

    def test_create_patient(self):
        c = _make_connector()
        data = {"first_name": "Bob", "last_name": "Smith", "email": "bob@test.com"}
        with patch.object(c, "_request", return_value={"id": "p2", **data}) as mock:
            result = c.create_patient(data)
        assert result["id"] == "p2"
        mock.assert_called_once_with("POST", "/patients", json=data)

    def test_update_patient(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={"id": "p1", "email": "new@b.com"}) as mock:
            result = c.update_patient("p1", {"email": "new@b.com"})
        assert result["email"] == "new@b.com"
        mock.assert_called_once_with("PATCH", "/patients/p1", json={"email": "new@b.com"})


# ── Appointments ─────────────────────────────────────────────────────────────────────────


class TestPabauAppointments:
    def test_create_appointment_injects_patient_id(self):
        c = _make_connector()
        data = {"start_time": "2026-06-01T10:00:00Z", "service_id": "svc-1"}
        with patch.object(c, "_request", return_value={"id": "a1"}) as mock:
            result = c.create_appointment("p1", data)
        assert result["id"] == "a1"
        mock.assert_called_once_with("POST", "/appointments", json={"start_time": "2026-06-01T10:00:00Z", "service_id": "svc-1", "patient_id": "p1"})

    def test_update_appointment(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={"id": "a1", "status": "confirmed"}) as mock:
            result = c.update_appointment("a1", {"status": "confirmed"})
        assert result["status"] == "confirmed"
        mock.assert_called_once_with("PATCH", "/appointments/a1", json={"status": "confirmed"})

    def test_cancel_appointment_returns_true(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value=None):
            assert c.cancel_appointment("a1") is True

    def test_cancel_appointment_returns_false_on_error(self):
        c = _make_connector()
        with patch.object(c, "_request", side_effect=ConnectorError("pabau", "DELETE", "fail")):
            assert c.cancel_appointment("a1") is False

    def test_get_appointment_returns_dict(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={"id": "a1"}) as mock:
            result = c.get_appointment("a1")
        assert result == {"id": "a1"}
        mock.assert_called_once_with("GET", "/appointments/a1")

    def test_get_appointment_returns_none_on_404(self):
        c = _make_connector()
        with patch.object(c, "_request", side_effect=ConnectorNotFoundError("pabau", "GET", "not found")):
            result = c.get_appointment("a1")
        assert result is None

    def test_list_appointments_passes_params(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={"items": []}) as mock:
            c.list_appointments("tid", status="confirmed", provider="dr1",
                                date_from="2026-06-01", date_to="2026-06-30",
                                patient_id="p1", offset=10, limit=25)
        mock.assert_called_once_with("GET", "/appointments", params={
            "offset": 10, "limit": 25, "status": "confirmed", "provider": "dr1",
            "date_from": "2026-06-01", "date_to": "2026-06-30", "patient_id": "p1",
        })

    def test_list_appointments_minimal_params(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={"items": []}) as mock:
            c.list_appointments("tid")
        mock.assert_called_once_with("GET", "/appointments", params={"offset": 0, "limit": 50})

    def test_list_appointments_normalizes_flat_dict(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={"appointments": [{"id": "a1"}], "total": 1}):
            result = c.list_appointments("tid")
        assert result == {"items": [{"id": "a1"}], "total": 1}

    def test_list_appointments_normalizes_data_dict(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={"data": [{"id": "a2"}], "total_entries": 5}):
            result = c.list_appointments("tid")
        assert result == {"items": [{"id": "a2"}], "total": 5}

    def test_list_appointments_passthrough_items(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={"items": [{"id": "a3"}], "total": 3}):
            result = c.list_appointments("tid")
        assert result == {"items": [{"id": "a3"}], "total": 3}

    def test_get_patient_appointments_from_dict(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={"items": [{"id": "a1"}]}):
            result = c.get_patient_appointments("p1")
        assert result == [{"id": "a1"}]

    def test_get_patient_appointments_from_list(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value=[{"id": "a1"}]):
            result = c.get_patient_appointments("p1")
        assert result == [{"id": "a1"}]

    def test_get_patient_appointments_empty(self):
        c = _make_connector()
        with patch.object(c, "_request", return_value={}):
            result = c.get_patient_appointments("p1")
        assert result == []


# ── Slots ────────────────────────────────────────────────────────────────────────────────


class TestPabauSlots:
    def test_search_available_slots_not_implemented(self):
        c = _make_connector()
        with pytest.raises(NotImplementedError):
            c.search_available_slots("dr1", "2026-06-01")


# ── Webhooks ─────────────────────────────────────────────────────────────────────────────


class TestPabauWebhooks:
    def test_verify_signature_valid(self):
        c = _make_connector(webhook_secret="mysecret")
        payload = b'{"event":"test"}'
        import hashlib
        import hmac
        real_sig = hmac.new(b"mysecret", payload, hashlib.sha256).hexdigest()
        assert c.verify_webhook_signature(payload, real_sig) is True

    def test_verify_signature_invalid(self):
        c = _make_connector(webhook_secret="mysecret")
        assert c.verify_webhook_signature(b'{"event":"test"}', "invalid_sig") is False

    def test_verify_signature_no_secret_rejects(self):
        c = _make_connector(webhook_secret="")
        assert c.verify_webhook_signature(b"{}", "anything") is False

    def test_parse_webhook_event(self):
        c = _make_connector()
        payload = {"event": "appointment.created", "data": {"id": "a1"}}
        result = c.parse_webhook_event(payload)
        assert result["event"] == "appointment.created"
        assert result["resource"] == {"id": "a1"}

    def test_parse_webhook_event_unknown_event(self):
        c = _make_connector()
        result = c.parse_webhook_event({"foo": "bar"})
        assert result["event"] == "unknown"
        assert result["resource"] == {}
