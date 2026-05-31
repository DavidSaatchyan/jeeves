from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.core.compliance.retention import (
    RetentionPolicy,
    apply_retention_policy,
    cleanup_expired_records,
)


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
def _mock_retention_config():
    with patch("app.core.compliance.retention.get_yaml_config") as m:
        m.return_value = {
            "compliance": {
                "retention": {
                    "audit_log": 1095,
                    "consent_log": 2190,
                    "messages": 730,
                    "patient_records": 3650,
                }
            }
        }
        yield


class TestApplyRetentionPolicy:
    def test_deletes_expired_audit_logs(self, mock_db, tenant_id):
        expired_ids = [uuid4(), uuid4()]
        mock_db.execute.return_value.scalars.return_value.all.return_value = expired_ids
        result = apply_retention_policy(mock_db, str(tenant_id))
        assert result["audit_logs_deleted"] == 2

    def test_returns_zero_when_none_expired(self, mock_db, tenant_id):
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        result = apply_retention_policy(mock_db, str(tenant_id))
        assert result["audit_logs_deleted"] == 0


class TestCleanupExpiredRecords:
    def test_deletes_expired_audit_logs(self, mock_db):
        mock_db.execute.return_value.rowcount = 3
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        result = cleanup_expired_records(mock_db)
        assert result["audit_logs_deleted"] == 3
        assert result["consent_logs_expired"] == 0

    def test_expires_granted_consents_past_expiry(self, mock_db):
        mock_db.execute.return_value.rowcount = 0
        expired_consent = MagicMock()
        expired_consent.status = "granted"
        mock_db.execute.return_value.scalars.return_value.all.return_value = [expired_consent]
        result = cleanup_expired_records(mock_db)
        assert result["consent_logs_expired"] == 1
        assert expired_consent.status == "expired"

    def test_handles_no_expired_records(self, mock_db):
        mock_db.execute.return_value.rowcount = 0
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        result = cleanup_expired_records(mock_db)
        assert result["audit_logs_deleted"] == 0
        assert result["consent_logs_expired"] == 0


class TestRetentionPolicyGetPolicy:
    def test_returns_timedelta_for_known_type(self):
        result = RetentionPolicy.get_policy("audit_log")
        assert result == timedelta(days=1095)

    def test_returns_default_for_unknown_type(self):
        result = RetentionPolicy.get_policy("unknown_type")
        assert result == timedelta(days=365)


class TestRetentionPolicyApplyPolicy:
    def test_sets_gdpr_data_retention_on_patient(self, mock_db):
        patient = MagicMock()
        RetentionPolicy.apply_policy(mock_db, patient)
        assert patient.gdpr_data_retention == "3650d"
        mock_db.flush.assert_called_once()


class TestRetentionPolicyFindExpiredRecords:
    def test_returns_expired_audit_logs(self, mock_db, tenant_id):
        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            MagicMock(),
            MagicMock(),
        ]
        result = RetentionPolicy.find_expired_records(mock_db, tenant_id)
        assert len(result) == 2

    def test_returns_empty_when_none_expired(self, mock_db, tenant_id):
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        result = RetentionPolicy.find_expired_records(mock_db, tenant_id)
        assert result == []


class TestRetentionPolicyAnonymizePatient:
    def test_anonymizes_patient_data(self, mock_db, patient_id):
        patient = MagicMock()
        mock_db.get.return_value = patient
        result = RetentionPolicy.anonymize_patient(mock_db, patient_id)
        assert result is True
        assert patient.first_name == "[ANONYMIZED]"
        assert patient.last_name == "[ANONYMIZED]"
        assert patient.email is None
        assert patient.phone == "[ANONYMIZED]"
        assert patient.date_of_birth is None
        assert patient.gender is None
        assert patient.extra_data == {}

    def test_returns_false_when_patient_not_found(self, mock_db, patient_id):
        mock_db.get.return_value = None
        result = RetentionPolicy.anonymize_patient(mock_db, patient_id)
        assert result is False


class TestRetentionPolicyDeleteExpired:
    def test_deletes_expired_records(self, mock_db, tenant_id):
        expired = [MagicMock(), MagicMock()]
        expired[0].id = uuid4()
        expired[1].id = uuid4()
        mock_db.execute.return_value.scalars.return_value.all.return_value = expired
        result = RetentionPolicy.delete_expired(mock_db, tenant_id)
        assert result == 2

    def test_returns_zero_when_none_expired(self, mock_db, tenant_id):
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        result = RetentionPolicy.delete_expired(mock_db, tenant_id)
        assert result == 0
