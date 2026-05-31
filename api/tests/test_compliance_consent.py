from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.core.compliance.consent import (
    ConsentManager,
    check_patient_consent,
    grant_consent,
    revoke_consent,
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


def _make_consent_log(
    patient_id: UUID,
    tenant_id: UUID,
    consent_type: str = "marketing",
    status: str = "granted",
    expires_at: datetime | None = None,
) -> MagicMock:
    log = MagicMock()
    log.id = uuid4()
    log.patient_id = patient_id
    log.tenant_id = tenant_id
    log.type = consent_type
    log.status = status
    log.channel = "widget"
    log.consent_text = "I agree to receive marketing emails"
    log.granted_at = datetime.utcnow()
    log.expires_at = expires_at
    log.ip_address = "127.0.0.1"
    log.user_agent = "test-agent"
    return log


class TestCheckPatientConsent:
    def test_returns_true_when_granted(self, mock_db, tenant_id, patient_id):
        log = _make_consent_log(patient_id, tenant_id)
        mock_db.execute.return_value.scalar_one_or_none.return_value = log
        assert check_patient_consent(mock_db, patient_id, "marketing", tenant_id) is True

    def test_returns_false_when_no_consent(self, mock_db, tenant_id, patient_id):
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        assert check_patient_consent(mock_db, patient_id, "marketing", tenant_id) is False

    def test_returns_false_when_expired(self, mock_db, tenant_id, patient_id):
        expired = _make_consent_log(
            patient_id, tenant_id, expires_at=datetime.utcnow() - timedelta(days=1)
        )
        mock_db.execute.return_value.scalar_one_or_none.return_value = expired
        assert check_patient_consent(mock_db, patient_id, "marketing", tenant_id) is False

    def test_returns_true_when_no_expiry(self, mock_db, tenant_id, patient_id):
        log = _make_consent_log(patient_id, tenant_id, expires_at=None)
        mock_db.execute.return_value.scalar_one_or_none.return_value = log
        assert check_patient_consent(mock_db, patient_id, "marketing", tenant_id) is True


class TestGrantConsent:
    def test_creates_consent_entry(self, mock_db, tenant_id, patient_id):
        entry = grant_consent(
            db=mock_db,
            patient_id=patient_id,
            consent_type="marketing",
            channel="widget",
            consent_text="I agree",
            tenant_id=tenant_id,
        )
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        assert entry.status == "granted"
        assert entry.type == "marketing"
        assert entry.channel == "widget"

    def test_with_expiry_and_metadata(self, mock_db, tenant_id, patient_id):
        future = datetime.utcnow() + timedelta(days=30)
        entry = grant_consent(
            db=mock_db,
            patient_id=patient_id,
            consent_type="data_processing",
            channel="web",
            consent_text="I agree to data processing",
            tenant_id=tenant_id,
            ip_address="10.0.0.1",
            user_agent="Chrome",
            expires_at=future,
        )
        assert entry.expires_at == future
        assert entry.ip_address == "10.0.0.1"
        assert entry.user_agent == "Chrome"


class TestRevokeConsent:
    def test_revokes_latest_consent(self, mock_db, tenant_id, patient_id):
        log = _make_consent_log(patient_id, tenant_id)
        mock_db.execute.return_value.scalar_one_or_none.return_value = log
        result = revoke_consent(mock_db, patient_id, "marketing", tenant_id)
        assert result.status == "revoked"
        assert result.revoked_at is not None

    def test_returns_none_when_no_granted_consent(self, mock_db, tenant_id, patient_id):
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        result = revoke_consent(mock_db, patient_id, "marketing", tenant_id)
        assert result is None


class TestConsentManagerCapture:
    def test_delegates_to_grant_consent(self, mock_db, tenant_id, patient_id):
        entry = ConsentManager.capture(
            db=mock_db,
            patient_id=patient_id,
            consent_type="marketing",
            channel="whatsapp",
            consent_text="I agree",
            tenant_id=tenant_id,
        )
        mock_db.add.assert_called_once()
        assert entry.status == "granted"


class TestConsentManagerRevoke:
    def test_revokes_by_id(self, mock_db):
        consent_id = uuid4()
        log = MagicMock()
        log.status = "granted"
        mock_db.get.return_value = log
        assert ConsentManager.revoke(mock_db, consent_id) is True
        assert log.status == "revoked"

    def test_returns_false_if_not_found(self, mock_db):
        mock_db.get.return_value = None
        assert ConsentManager.revoke(mock_db, uuid4()) is False

    def test_returns_false_if_already_revoked(self, mock_db):
        log = MagicMock()
        log.status = "revoked"
        mock_db.get.return_value = log
        assert ConsentManager.revoke(mock_db, uuid4()) is False


class TestConsentManagerRenew:
    def test_creates_new_entry_from_original(self, mock_db, tenant_id, patient_id):
        original = _make_consent_log(patient_id, tenant_id)
        mock_db.get.return_value = original
        future = datetime.utcnow() + timedelta(days=90)
        entry = ConsentManager.renew(mock_db, original.id, expires_at=future)
        assert entry is not None
        assert entry.status == "granted"
        assert entry.type == original.type
        assert entry.tenant_id == original.tenant_id
        assert entry.patient_id == original.patient_id
        assert entry.consent_text == original.consent_text

    def test_returns_none_if_not_found(self, mock_db):
        mock_db.get.return_value = None
        assert ConsentManager.renew(mock_db, uuid4()) is None


class TestConsentManagerIsValid:
    def test_delegates_to_check(self, mock_db, tenant_id, patient_id):
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_consent_log(
            patient_id, tenant_id
        )
        assert ConsentManager.is_valid(mock_db, patient_id, "marketing", tenant_id) is True

    def test_returns_false_for_invalid(self, mock_db, tenant_id, patient_id):
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        assert ConsentManager.is_valid(mock_db, patient_id, "marketing", tenant_id) is False


class TestConsentManagerGetActiveConsents:
    def test_returns_active_consents(self, mock_db, tenant_id, patient_id):
        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            _make_consent_log(patient_id, tenant_id),
        ]
        result = ConsentManager.get_active_consents(mock_db, patient_id, tenant_id)
        assert len(result) == 1

    def test_returns_empty(self, mock_db, tenant_id, patient_id):
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        result = ConsentManager.get_active_consents(mock_db, patient_id, tenant_id)
        assert result == []


class TestConsentManagerGetExpiringConsents:
    def test_returns_expiring_before_date(self, mock_db):
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        result = ConsentManager.get_expiring_consents(mock_db, datetime.utcnow())
        assert result == []

    def test_includes_expiring_consents(self, mock_db):
        mock_db.execute.return_value.scalars.return_value.all.return_value = [MagicMock(), MagicMock()]
        result = ConsentManager.get_expiring_consents(mock_db, datetime.utcnow())
        assert len(result) == 2


class TestConsentManagerGetConsentHistory:
    def test_returns_all_entries(self, mock_db, patient_id):
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        result = ConsentManager.get_consent_history(mock_db, patient_id)
        assert result == []

    def test_filters_by_type(self, mock_db, patient_id):
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        result = ConsentManager.get_consent_history(mock_db, patient_id, consent_type="marketing")
        assert result == []

    def test_returns_multiple_entries(self, mock_db, patient_id):
        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            _make_consent_log(patient_id, uuid4()),
            _make_consent_log(patient_id, uuid4()),
        ]
        result = ConsentManager.get_consent_history(mock_db, patient_id)
        assert len(result) == 2
