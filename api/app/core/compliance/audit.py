from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timedelta
from typing import Any, Sequence
from uuid import UUID

import logging
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import get_settings
from ...models import AuditLog

logger = logging.getLogger("jeeves.compliance.audit")


def _retention_cutoff(days: int) -> datetime:
    now = datetime.utcnow()
    return now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days)


def record_audit_event(
    db: Session,
    tenant_id: UUID,
    action: str,
    actor_type: str,
    actor_id: str,
    patient_id: UUID | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    settings = get_settings()
    entry = AuditLog(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        patient_id=patient_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or {},
        ip_address=ip_address,
        timestamp=datetime.utcnow(),
        retention_until=_retention_cutoff(settings.compliance_audit_retention_days),
    )
    db.add(entry)
    db.flush()
    logger.info("audit %s actor=%s/%s resource=%s/%s", action, actor_type, actor_id, resource_type, resource_id)
    return entry


def record_phi_access(
    db: Session,
    tenant_id: UUID,
    patient_id: UUID,
    actor_type: str,
    actor_id: str,
    phi_fields: list[str],
    ip_address: str | None = None,
) -> AuditLog:
    return record_audit_event(
        db=db,
        tenant_id=tenant_id,
        action="phi_accessed",
        actor_type=actor_type,
        actor_id=actor_id,
        patient_id=patient_id,
        resource_type="phi",
        details={"phi_fields": phi_fields},
        ip_address=ip_address,
    )


class AuditLogger:
    """Class-based API matching PLAN-PHASE2-COMPLIANCE 2.2 spec."""

    @staticmethod
    def log(
        db: Session,
        actor_type: str,
        actor_id: str,
        action: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        details: dict[str, Any] | None = None,
        tenant_id: UUID | None = None,
        patient_id: UUID | None = None,
        ip_address: str | None = None,
    ) -> AuditLog:
        if not tenant_id:
            raise ValueError("tenant_id is required")
        return record_audit_event(
            db=db,
            tenant_id=tenant_id,
            action=action,
            actor_type=actor_type,
            actor_id=actor_id,
            patient_id=patient_id,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
        )

    @staticmethod
    def query(
        db: Session,
        tenant_id: UUID,
        action: str | None = None,
        patient_id: UUID | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[AuditLog]:
        q = select(AuditLog).where(AuditLog.tenant_id == tenant_id)
        if action:
            q = q.where(AuditLog.action == action)
        if patient_id:
            q = q.where(AuditLog.patient_id == patient_id)
        if from_date:
            q = q.where(AuditLog.timestamp >= from_date)
        if to_date:
            q = q.where(AuditLog.timestamp <= to_date)
        return db.execute(
            q.order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit)
        ).scalars().all()

    @staticmethod
    def get_patient_timeline(db: Session, patient_id: UUID, tenant_id: UUID) -> Sequence[AuditLog]:
        return db.execute(
            select(AuditLog).where(
                AuditLog.patient_id == patient_id,
                AuditLog.tenant_id == tenant_id,
            ).order_by(AuditLog.timestamp.desc())
        ).scalars().all()

    @staticmethod
    def export(
        db: Session,
        tenant_id: UUID,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> str:
        rows = AuditLogger.query(db, tenant_id, from_date=from_date, to_date=to_date, limit=5000)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["id", "timestamp", "action", "actor_type", "actor_id", "patient_id", "resource_type", "resource_id", "ip_address"])
        for r in rows:
            w.writerow([
                str(r.id), r.timestamp.isoformat(), r.action, r.actor_type, r.actor_id,
                str(r.patient_id) if r.patient_id else "",
                r.resource_type or "", r.resource_id or "", r.ip_address or "",
            ])
        return buf.getvalue()
