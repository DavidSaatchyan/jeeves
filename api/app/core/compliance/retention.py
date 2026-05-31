from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

import logging
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ...config import get_yaml_config
from ...models import AuditLog, ConsentLog, Patient

logger = logging.getLogger("jeeves.compliance.retention")

_RETENTION_DEFAULTS: dict[str, int] = {
    "audit_log": 1095,
    "consent_log": 2190,
    "messages": 730,
    "patient_records": 3650,
    "appointments": 1095,
}


def _get_retention_config() -> dict[str, int]:
    yaml_config = get_yaml_config()
    configured = yaml_config.get("compliance", {}).get("retention", {})
    result = dict(_RETENTION_DEFAULTS)
    result.update(configured)
    return result


def apply_retention_policy(db: Session, tenant_id: str) -> dict[str, int]:
    policies = _get_retention_config()
    cutoff = datetime.utcnow() - timedelta(days=policies.get("audit_log", 1095))

    expired = db.execute(
        select(AuditLog.id).where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.timestamp < cutoff,
        )
    ).scalars().all()

    if expired:
        db.execute(delete(AuditLog).where(AuditLog.id.in_(expired)))
        logger.info("retention: deleted %d audit log rows for tenant %s", len(expired), tenant_id)

    return {"audit_logs_deleted": len(expired)}


def cleanup_expired_records(db: Session) -> dict[str, int]:
    total: dict[str, int] = {"audit_logs_deleted": 0, "consent_logs_expired": 0}

    policies = _get_retention_config()
    cutoff = datetime.utcnow() - timedelta(days=policies.get("audit_log", 1095))

    result = db.execute(delete(AuditLog).where(AuditLog.timestamp < cutoff))
    total["audit_logs_deleted"] = result.rowcount

    expired_consents = db.execute(
        select(ConsentLog).where(
            ConsentLog.status == "granted",
            ConsentLog.expires_at < datetime.utcnow(),
        )
    ).scalars().all()
    for c in expired_consents:
        c.status = "expired"
    total["consent_logs_expired"] = len(expired_consents)
    db.flush()

    if total["audit_logs_deleted"] or total["consent_logs_expired"]:
        logger.info("cleanup complete: %s", total)

    return total


class RetentionPolicy:
    """Class-based API matching PLAN-PHASE2-COMPLIANCE 2.2 spec."""

    @staticmethod
    def get_policy(data_type: str) -> timedelta:
        policies = _get_retention_config()
        return timedelta(days=policies.get(data_type, 365))

    @staticmethod
    def apply_policy(db: Session, patient: Patient) -> None:
        policies = _get_retention_config()
        days = policies.get("patient_records", 3650)
        patient.gdpr_data_retention = f"{days}d"
        db.flush()

    @staticmethod
    def find_expired_records(db: Session, tenant_id: UUID) -> list[AuditLog]:
        policies = _get_retention_config()
        cutoff = datetime.utcnow() - timedelta(days=policies.get("audit_log", 1095))
        return list(db.execute(
            select(AuditLog).where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.timestamp < cutoff,
            ).order_by(AuditLog.timestamp.asc())
        ).scalars().all())

    @staticmethod
    def anonymize_patient(db: Session, patient_id: UUID) -> bool:
        patient = db.get(Patient, patient_id)
        if not patient:
            return False
        patient.first_name = "[ANONYMIZED]"
        patient.last_name = "[ANONYMIZED]"
        patient.email = None
        patient.phone = "[ANONYMIZED]"
        patient.date_of_birth = None
        patient.gender = None
        patient.extra_data = {}
        db.flush()
        logger.info("anonymized patient %s", patient_id)
        return True

    @staticmethod
    def delete_expired(db: Session, tenant_id: UUID) -> int:
        records = RetentionPolicy.find_expired_records(db, tenant_id)
        if not records:
            return 0
        ids = [r.id for r in records]
        db.execute(delete(AuditLog).where(AuditLog.id.in_(ids)))
        logger.info("deleted %d expired audit logs for tenant %s", len(ids), tenant_id)
        return len(ids)
