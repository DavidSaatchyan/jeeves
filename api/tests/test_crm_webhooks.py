from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.crypto import ConnectorError
from app.integrations.crm import webhooks as wh


@pytest.fixture
def tenant_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def mock_db() -> MagicMock:
    return MagicMock(name="db_session")


@pytest.fixture
def mock_conn(tenant_id: uuid.UUID) -> MagicMock:
    conn = MagicMock(name="crm_connection")
    conn.id = uuid.uuid4()
    conn.tenant_id = tenant_id
    conn.provider = "zoho"
    conn.config = {"client_id": "c", "client_secret": "s", "refresh_token": "r"}
    conn.webhook_secret = "wh_secret"
    return conn


@pytest.fixture
def mock_request() -> MagicMock:
    req = MagicMock(name="request")
    req.headers = {"X-Webhook-Signature": "valid_sig"}
    req.body = AsyncMock(return_value=b'{"event": {"type": "test"}}')
    return req


@pytest.fixture
def mock_adapter() -> MagicMock:
    adapter = MagicMock(name="crm_adapter")
    adapter.phi_safe = True
    adapter.verify_webhook_signature.return_value = True
    adapter.parse_webhook_event.return_value = {"event": "contact.created", "resource": {"id": "ext1", "first_name": "John", "last_name": "Doe"}}
    return adapter


# ── _get_connector ──────────────────────────────────────────────────────


class TestGetConnector:
    def test_returns_connection(self, mock_db: MagicMock, mock_conn: MagicMock):
        q = mock_db.query
        q.return_value.filter.return_value.filter.return_value.first.return_value = mock_conn
        result = wh._get_connector("zoho", mock_db, tenant_id=mock_conn.tenant_id)
        assert result is mock_conn

    def test_raises_404_when_not_found(self, mock_db: MagicMock):
        q = mock_db.query
        q.return_value.filter.return_value.first.return_value = None
        with pytest.raises(HTTPException) as excinfo:
            wh._get_connector("nonexistent", mock_db)
        assert excinfo.value.status_code == 404

    def test_filters_by_tenant(self, mock_db: MagicMock, mock_conn: MagicMock, tenant_id: uuid.UUID):
        q = mock_db.query
        q.return_value.filter.return_value.filter.return_value.first.return_value = mock_conn
        wh._get_connector("zoho", mock_db, tenant_id=tenant_id)
        assert q.called


# ── _verify_signature ───────────────────────────────────────────────────


class TestVerifySignature:
    def test_adapter_verifies(self, mock_adapter: MagicMock):
        with patch("app.integrations.crm.get_crm_adapter", return_value=mock_adapter):
            result = wh._verify_signature("zoho", b"{}", "sig", {})
            assert result is True
            mock_adapter.verify_webhook_signature.assert_called_once_with(b"{}", "sig")

    def test_adapter_rejects(self, mock_adapter: MagicMock):
        mock_adapter.verify_webhook_signature.return_value = False
        with patch("app.integrations.crm.get_crm_adapter", return_value=mock_adapter):
            result = wh._verify_signature("zoho", b"{}", "bad_sig", {})
            assert result is False

    def test_fallback_to_secret(self):
        with patch("app.integrations.crm.get_crm_adapter", side_effect=ConnectorError(provider="zoho", operation="get_adapter", message="Unknown")):
            with patch("app.integrations.crm.webhooks.hmac.new") as mock_hmac:
                mock_hmac.return_value.hexdigest.return_value = "expected_hash"
                with patch("app.integrations.crm.webhooks.hmac.compare_digest", return_value=True):
                    result = wh._verify_signature("zoho", b"{}", "expected_hash", {"webhook_secret": "secret"})
                    assert result is True

    def test_fallback_no_secret_returns_true(self):
        with patch("app.integrations.crm.get_crm_adapter", side_effect=ConnectorError(provider="zoho", operation="get_adapter", message="Unknown")):
            result = wh._verify_signature("zoho", b"{}", "sig", {})
            assert result is True


# ── _upsert_patient ────────────────────────────────────────────────────


class TestUpsertPatient:
    def test_creates_new_patient(self, mock_db: MagicMock, tenant_id: uuid.UUID):
        q = mock_db.query
        q.return_value.filter.return_value.first.return_value = None
        mock_patient_instance = MagicMock(name="patient_instance")
        mock_patient_instance.id = uuid.uuid4()
        with patch.object(wh, "Patient", return_value=mock_patient_instance):
            result = wh._upsert_patient(mock_db, tenant_id, {"id": "ext1", "first_name": "John", "last_name": "Doe", "email": "j@d.com"})
            assert result is mock_patient_instance

    def test_raises_400_when_missing_external_id(self, mock_db: MagicMock, tenant_id: uuid.UUID):
        with pytest.raises(HTTPException) as excinfo:
            wh._upsert_patient(mock_db, tenant_id, {"first_name": "John"})
        assert excinfo.value.status_code == 400

    def test_updates_existing_patient(self, mock_db: MagicMock, tenant_id: uuid.UUID):
        existing = MagicMock(name="existing_patient")
        existing.first_name = "Old"
        existing.last_name = ""
        existing.email = None
        existing.phone = ""
        q = mock_db.query
        q.return_value.filter.return_value.first.return_value = existing
        wh._upsert_patient(mock_db, tenant_id, {"id": "ext1", "first_name": "New", "email": "new@email.com"})
        assert existing.first_name == "New"
        assert existing.email == "new@email.com"
        mock_db.flush.assert_called_once()


# ── _sync_appointment_from_webhook ────────────────────────────────────


class TestSyncAppointmentFromWebhook:
    def test_creates_new_cache_entry(self, mock_db: MagicMock, tenant_id: uuid.UUID):
        q = mock_db.query
        q.return_value.filter.return_value.first.return_value = None
        mock_cache_instance = MagicMock(name="cache_instance")
        mock_cache_instance.id = uuid.uuid4()
        with patch.object(wh, "AppointmentCache", return_value=mock_cache_instance):
            result = wh._sync_appointment_from_webhook(mock_db, tenant_id, uuid.uuid4(), {"id": "a1", "status": "scheduled"})
            assert result is mock_cache_instance

    def test_updates_existing_cache_entry(self, mock_db: MagicMock, tenant_id: uuid.UUID):
        existing = MagicMock(name="existing_cache")
        existing.status = "scheduled"
        q = mock_db.query
        q.return_value.filter.return_value.first.return_value = existing
        wh._sync_appointment_from_webhook(mock_db, tenant_id, uuid.uuid4(), {"id": "a1", "status": "completed"})
        assert existing.status == "completed"
        mock_db.flush.assert_called_once()


# ── _handle_webhook ────────────────────────────────────────────────────


class TestHandleWebhook:
    def test_patient_event(self, mock_request: MagicMock, mock_conn: MagicMock, mock_adapter: MagicMock, tenant_id: uuid.UUID):
        mock_patient_instance = MagicMock(name="patient_instance")
        mock_patient_instance.id = uuid.uuid4()
        with patch("app.integrations.crm.webhooks._get_connector", return_value=mock_conn):
            with patch("app.integrations.crm.get_crm_adapter", return_value=mock_adapter):
                with patch("app.integrations.crm.webhooks._verify_signature", return_value=True):
                    with patch.object(wh, "Patient", return_value=mock_patient_instance):
                        result = wh._handle_webhook("zoho", json.dumps({"event": {"type": "contact.created"}, "resource": {"id": "ext1"}}).encode(), mock_request, MagicMock(), tenant_id)
        assert result["ok"] is True
        assert result["entity"] == "patient"

    def test_appointment_event(self, mock_request: MagicMock, mock_conn: MagicMock, mock_adapter: MagicMock, tenant_id: uuid.UUID):
        mock_adapter.parse_webhook_event.return_value = {"event": "appointment.created", "resource": {"id": "a1", "patient_id": "ext_p1", "provider_name": "Dr. X", "start_time": "2025-01-01T10:00", "end_time": "2025-01-01T10:30"}}
        mock_found_patient = MagicMock(name="found_patient")
        mock_found_patient.id = uuid.uuid4()
        mock_cache_instance = MagicMock(name="cache_instance")
        mock_cache_instance.id = uuid.uuid4()
        mock_db = MagicMock()
        q = mock_db.query
        q.return_value.filter.return_value.filter.return_value.first.side_effect = [mock_conn, mock_found_patient]
        with patch("app.integrations.crm.get_crm_adapter", return_value=mock_adapter):
            with patch.object(wh, "_verify_signature", return_value=True):
                with patch.object(wh, "AppointmentCache", return_value=mock_cache_instance):
                    result = wh._handle_webhook("zoho", json.dumps({"id": "a1"}).encode(), mock_request, mock_db, tenant_id)
        assert result["ok"] is True
        assert result["entity"] == "appointment"

    def test_invalid_json_raises_400(self, mock_db: MagicMock, mock_request: MagicMock):
        with pytest.raises(HTTPException) as excinfo:
            wh._handle_webhook("zoho", b"not json", mock_request, mock_db)
        assert excinfo.value.status_code == 400

    def test_bad_signature_raises_401(self, mock_request: MagicMock, mock_conn: MagicMock):
        with patch("app.integrations.crm.webhooks._get_connector", return_value=mock_conn):
            with patch("app.integrations.crm.webhooks._verify_signature", return_value=False):
                with pytest.raises(HTTPException) as excinfo:
                    wh._handle_webhook("zoho", b"{}", mock_request, MagicMock())
        assert excinfo.value.status_code == 401

    def test_unknown_event_type(self, mock_request: MagicMock, mock_conn: MagicMock, mock_adapter: MagicMock):
        mock_adapter.parse_webhook_event.return_value = {"event": "some.unknown.event", "resource": {}}
        with patch("app.integrations.crm.webhooks._get_connector", return_value=mock_conn):
            with patch("app.integrations.crm.get_crm_adapter", return_value=mock_adapter):
                with patch("app.integrations.crm.webhooks._verify_signature", return_value=True):
                    result = wh._handle_webhook("zoho", b"{}", mock_request, MagicMock(), tenant_id=uuid.uuid4())
        assert result["ok"] is True
        assert result["handled"] is False
        assert result["event"] == "some.unknown.event"

    def test_missing_linked_patient_raises_404(self, mock_request: MagicMock, mock_conn: MagicMock, mock_adapter: MagicMock):
        mock_adapter.parse_webhook_event.return_value = {"event": "appointment.updated", "resource": {"id": "a1", "patient_id": "no_such_patient"}}
        mock_db = MagicMock()
        q = mock_db.query
        q.return_value.filter.return_value.first.return_value = None
        with patch("app.integrations.crm.webhooks._get_connector", return_value=mock_conn):
            with patch("app.integrations.crm.get_crm_adapter", return_value=mock_adapter):
                with patch("app.integrations.crm.webhooks._verify_signature", return_value=True):
                    with pytest.raises(HTTPException) as excinfo:
                        wh._handle_webhook("zoho", b"{}", mock_request, mock_db, tenant_id=uuid.uuid4())
        assert excinfo.value.status_code == 404

    def test_phi_minimization_for_non_safe_adapter(self, mock_request: MagicMock, mock_conn: MagicMock, mock_adapter: MagicMock, tenant_id: uuid.UUID):
        mock_adapter.phi_safe = False
        mock_adapter.parse_webhook_event.return_value = {"event": "contact.created", "resource": {"id": "ext1", "first_name": "John", "ssn": "123-45-6789"}}
        mock_patient_instance = MagicMock(name="patient_instance")
        mock_patient_instance.id = uuid.uuid4()
        with patch("app.integrations.crm.webhooks._get_connector", return_value=mock_conn):
            with patch("app.integrations.crm.get_crm_adapter", return_value=mock_adapter):
                with patch.object(wh, "Patient", return_value=mock_patient_instance):
                    with patch("app.integrations.crm.webhooks._verify_signature", return_value=True):
                        with patch("app.core.compliance.phi_minimization.mask_phi", return_value={"id": "ext1"}) as mock_mask:
                            wh._handle_webhook("zoho", b"{}", mock_request, MagicMock(), tenant_id)
                            mock_mask.assert_called_once()

    def test_phi_minimization_import_error_does_not_crash(self, mock_request: MagicMock, mock_conn: MagicMock, mock_adapter: MagicMock, tenant_id: uuid.UUID):
        mock_adapter.phi_safe = False
        mock_patient_instance = MagicMock(name="patient_instance")
        mock_patient_instance.id = uuid.uuid4()
        with patch("app.integrations.crm.webhooks._get_connector", return_value=mock_conn):
            with patch("app.integrations.crm.get_crm_adapter", return_value=mock_adapter):
                with patch.object(wh, "Patient", return_value=mock_patient_instance):
                    with patch("app.integrations.crm.webhooks._verify_signature", return_value=True):
                        with patch("app.core.compliance.phi_minimization.mask_phi", side_effect=ImportError("No module")):
                            result = wh._handle_webhook("zoho", b"{}", mock_request, MagicMock(), tenant_id)
                            assert result["ok"] is True


# ── _log_audit ──────────────────────────────────────────────────────────


class TestLogAudit:
    def test_creates_audit_entry(self, mock_db: MagicMock, tenant_id: uuid.UUID):
        patient_id = uuid.uuid4()
        wh._log_audit(mock_db, tenant_id, patient_id, "crm_zoho", "contact.created", "patient", "ext1")
        mock_db.add.assert_called_once()
        entry = mock_db.add.call_args[0][0]
        assert entry.tenant_id == tenant_id
        assert entry.patient_id == patient_id
        assert entry.action == "contact.created"
        assert entry.resource_type == "patient"
        assert entry.resource_id == "ext1"
        assert entry.details == {"source": "crm_webhook"}
        mock_db.flush.assert_called_once()

    def test_allows_none_patient_id(self, mock_db: MagicMock, tenant_id: uuid.UUID):
        wh._log_audit(mock_db, tenant_id, None, "system", "event", "resource", "rid")
        entry = mock_db.add.call_args[0][0]
        assert entry.patient_id is None


# ── Route handlers ─────────────────────────────────────────────────────


class TestRouteFunctions:
    @pytest.mark.asyncio
    async def test_webhook_zoho_calls_handle(self):
        mock_req = MagicMock(name="request")
        payload = json.dumps({"event": {"type": "test"}}).encode()
        mock_req.body = AsyncMock(return_value=payload)
        with patch.object(wh, "_handle_webhook") as mock_handle:
            await wh.webhook_zoho(mock_req, MagicMock())
            mock_handle.assert_called_once()
            args = mock_handle.call_args[0]
            assert args[0] == "zoho"
            assert args[1] == payload

    @pytest.mark.asyncio
    async def test_webhook_hubspot_calls_handle(self):
        mock_req = MagicMock(name="request")
        payload = json.dumps({"subscriptionType": "test"}).encode()
        mock_req.body = AsyncMock(return_value=payload)
        with patch.object(wh, "_handle_webhook") as mock_handle:
            await wh.webhook_hubspot(mock_req, MagicMock())
            mock_handle.assert_called_once()
            args = mock_handle.call_args[0]
            assert args[0] == "hubspot"
            assert args[1] == payload
