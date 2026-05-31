from __future__ import annotations

import uuid
from datetime import datetime
from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import ConsentLog


def check_patient_consent(
    db: Session,
    patient_id: UUID,
    consent_type: str,
    tenant_id: UUID,
) -> bool:
    result = db.execute(
        select(ConsentLog).where(
            ConsentLog.patient_id == patient_id,
            ConsentLog.tenant_id == tenant_id,
            ConsentLog.type == consent_type,
            ConsentLog.status == "granted",
        ).order_by(ConsentLog.granted_at.desc()).limit(1)
    ).scalar_one_or_none()
    if not result:
        return False
    if result.expires_at and result.expires_at < datetime.utcnow():
        return False
    return True


def grant_consent(
    db: Session,
    patient_id: UUID,
    consent_type: str,
    channel: str,
    consent_text: str,
    tenant_id: UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
    expires_at: datetime | None = None,
) -> ConsentLog:
    entry = ConsentLog(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        patient_id=patient_id,
        type=consent_type,
        status="granted",
        channel=channel,
        consent_text=consent_text,
        ip_address=ip_address,
        user_agent=user_agent,
        granted_at=datetime.utcnow(),
        expires_at=expires_at,
    )
    db.add(entry)
    db.flush()
    return entry


def revoke_consent(
    db: Session,
    patient_id: UUID,
    consent_type: str,
    tenant_id: UUID,
) -> ConsentLog | None:
    latest = db.execute(
        select(ConsentLog).where(
            ConsentLog.patient_id == patient_id,
            ConsentLog.tenant_id == tenant_id,
            ConsentLog.type == consent_type,
            ConsentLog.status == "granted",
        ).order_by(ConsentLog.granted_at.desc()).limit(1)
    ).scalar_one_or_none()
    if not latest:
        return None
    latest.status = "revoked"
    latest.revoked_at = datetime.utcnow()
    db.flush()
    return latest


class ConsentManager:
    """Class-based API matching PLAN-PHASE2-COMPLIANCE 2.2 spec."""

    @staticmethod
    def capture(
        db: Session,
        patient_id: UUID,
        consent_type: str,
        channel: str,
        consent_text: str,
        tenant_id: UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
        expires_at: datetime | None = None,
    ) -> ConsentLog:
        return grant_consent(db, patient_id, consent_type, channel, consent_text, tenant_id, ip_address, user_agent, expires_at)

    @staticmethod
    def revoke(db: Session, consent_id: UUID) -> bool:
        entry = db.get(ConsentLog, consent_id)
        if not entry or entry.status != "granted":
            return False
        entry.status = "revoked"
        entry.revoked_at = datetime.utcnow()
        db.flush()
        return True

    @staticmethod
    def renew(db: Session, consent_id: UUID, expires_at: datetime | None = None) -> ConsentLog | None:
        original = db.get(ConsentLog, consent_id)
        if not original:
            return None
        entry = ConsentLog(
            id=uuid.uuid4(),
            tenant_id=original.tenant_id,
            patient_id=original.patient_id,
            type=original.type,
            status="granted",
            channel=original.channel,
            consent_text=original.consent_text,
            granted_at=datetime.utcnow(),
            expires_at=expires_at,
        )
        db.add(entry)
        db.flush()
        return entry

    @staticmethod
    def is_valid(db: Session, patient_id: UUID, consent_type: str, tenant_id: UUID) -> bool:
        return check_patient_consent(db, patient_id, consent_type, tenant_id)

    @staticmethod
    def get_active_consents(db: Session, patient_id: UUID, tenant_id: UUID) -> Sequence[ConsentLog]:
        return db.execute(
            select(ConsentLog).where(
                ConsentLog.patient_id == patient_id,
                ConsentLog.tenant_id == tenant_id,
                ConsentLog.status == "granted",
            ).order_by(ConsentLog.granted_at.desc())
        ).scalars().all()

    @staticmethod
    def get_expiring_consents(db: Session, before: datetime) -> Sequence[ConsentLog]:
        return db.execute(
            select(ConsentLog).where(
                ConsentLog.status == "granted",
                ConsentLog.expires_at < before,
            ).order_by(ConsentLog.expires_at.asc())
        ).scalars().all()

    @staticmethod
    def get_consent_history(db: Session, patient_id: UUID, consent_type: str | None = None) -> Sequence[ConsentLog]:
        q = select(ConsentLog).where(ConsentLog.patient_id == patient_id)
        if consent_type:
            q = q.where(ConsentLog.type == consent_type)
        return db.execute(q.order_by(ConsentLog.granted_at.desc())).scalars().all()
