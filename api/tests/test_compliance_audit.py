from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.core.compliance.audit import AuditLogger, record_audit_event, record_phi_access


@pytest.fixture
def tenant_id() -> UUID:
    return uuid4()


@pytest.fixture
def patient_id() -> UUID:
    return uuid4()


@pytest.fixture
def mock_db() -> MagicMock:
    return MagicMock(spec=Session)


@pytest.fixture(autouse=True)
def _mock_settings():
    with patch("app.core.compliance.audit.get_settings") as m:
        settings = MagicMock()
        settings.compliance_audit_retention_days = 1095
        m.return_value = settings
        yield


class TestRecordAuditEvent:
    def test_creates_audit_log_entry(self, mock_db, tenant_id):
        entry = record_audit_event(
            db=mock_db,
            tenant_id=tenant_id,
            action="message_sent",
            actor_type="patient",
            actor_id="user_123",
        )
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        assert entry.action == "message_sent"
        assert entry.actor_type == "patient"
        assert entry.actor_id == "user_123"

    def test_includes_all_fields(self, mock_db, tenant_id, patient_id):
        entry = record_audit_event(
            db=mock_db,
            tenant_id=tenant_id,
            action="phi_accessed",
            actor_type="staff",
            actor_id="staff_42",
            patient_id=patient_id,
            resource_type="patient_record",
            resource_id="rec_999",
            details={"phi_fields": ["ssn", "email"]},
            ip_address="192.168.1.1",
        )
        assert entry.tenant_id == tenant_id
        assert entry.patient_id == patient_id
        assert entry.resource_type == "patient_record"
        assert entry.resource_id == "rec_999"
        assert entry.details == {"phi_fields": ["ssn", "email"]}
        assert entry.ip_address == "192.168.1.1"

    def test_sets_retention_until(self, mock_db, tenant_id):
        entry = record_audit_event(
            db=mock_db,
            tenant_id=tenant_id,
            action="data_deleted",
            actor_type="system",
            actor_id="system",
        )
        assert entry.retention_until is not None


class TestRecordPhiAccess:
    def test_records_phi_access(self, mock_db, tenant_id, patient_id):
        entry = record_phi_access(
            db=mock_db,
            tenant_id=tenant_id,
            patient_id=patient_id,
            actor_type="staff",
            actor_id="staff_42",
            phi_fields=["ssn", "diagnosis"],
            ip_address="10.0.0.1",
        )
        assert entry.action == "phi_accessed"
        assert entry.resource_type == "phi"
        assert entry.details["phi_fields"] == ["ssn", "diagnosis"]
        assert entry.patient_id == patient_id


class TestAuditLoggerLog:
    def test_log_creates_entry(self, mock_db, tenant_id):
        entry = AuditLogger.log(
            db=mock_db,
            actor_type="patient",
            actor_id="p_1",
            action="login",
            resource_type="session",
            resource_id="sess_1",
            tenant_id=tenant_id,
        )
        mock_db.add.assert_called_once()
        assert entry.action == "login"

    def test_raises_without_tenant_id(self, mock_db):
        with pytest.raises(ValueError, match="tenant_id is required"):
            AuditLogger.log(
                db=mock_db,
                actor_type="patient",
                actor_id="p_1",
                action="login",
            )


class TestAuditLoggerQuery:
    def test_queries_with_tenant_id(self, mock_db, tenant_id):
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        result = AuditLogger.query(mock_db, tenant_id)
        assert result == []
        mock_db.execute.assert_called_once()

    def test_filters_by_action(self, mock_db, tenant_id):
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        AuditLogger.query(mock_db, tenant_id, action="login")
        mock_db.execute.assert_called_once()

    def test_filters_by_patient(self, mock_db, tenant_id, patient_id):
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        AuditLogger.query(mock_db, tenant_id, patient_id=patient_id)
        mock_db.execute.assert_called_once()

    def test_filters_by_date_range(self, mock_db, tenant_id):
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        from_date = datetime(2024, 1, 1)
        to_date = datetime(2024, 12, 31)
        AuditLogger.query(mock_db, tenant_id, from_date=from_date, to_date=to_date)
        mock_db.execute.assert_called_once()


class TestAuditLoggerGetPatientTimeline:
    def test_returns_timeline(self, mock_db, tenant_id, patient_id):
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        result = AuditLogger.get_patient_timeline(mock_db, patient_id, tenant_id)
        assert result == []


class TestAuditLoggerExport:
    def test_returns_csv_string(self, mock_db, tenant_id):
        mock_log = MagicMock()
        mock_log.id = uuid4()
        mock_log.timestamp = datetime(2024, 6, 1, 12, 0, 0)
        mock_log.action = "login"
        mock_log.actor_type = "patient"
        mock_log.actor_id = "p_1"
        mock_log.patient_id = None
        mock_log.resource_type = None
        mock_log.resource_id = None
        mock_log.ip_address = None
        mock_db.execute.return_value.scalars.return_value.all.return_value = [mock_log]

        result = AuditLogger.export(mock_db, tenant_id)
        assert "id,timestamp,action,actor_type,actor_id" in result
        assert "login" in result

    def test_export_empty(self, mock_db, tenant_id):
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        result = AuditLogger.export(mock_db, tenant_id)
        lines = result.strip().split("\n")
        assert len(lines) == 1
