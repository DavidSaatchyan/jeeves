from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.compliance.audit import AuditLogger, record_audit_event
from ..core.compliance.consent import check_patient_consent, grant_consent, revoke_consent
from ..core.compliance.phi_minimization import strip_phi
from ..core.compliance.retention import RetentionPolicy, apply_retention_policy
from ..db import get_db
from ..models import AuditLog, Patient, Tenant
from .deps import get_admin_tenant
from .router import router


@router.get("/api/compliance/patients/{patient_id}/consent")
def api_get_patient_consent(
    patient_id: UUID,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    patient = db.get(Patient, patient_id)
    if not patient or patient.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Patient not found")

    consented = check_patient_consent(db, patient_id, "appointment", tenant.id)
    return {
        "patient_id": str(patient_id),
        "consent_status": patient.consent_status,
        "consent_timestamp": patient.consent_timestamp,
        "consent_channel": patient.consent_channel,
        "has_active_consent": consented,
    }


@router.post("/api/compliance/patients/{patient_id}/consent")
def api_grant_consent(
    patient_id: UUID,
    body: dict,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    request: Request = None,
):
    patient = db.get(Patient, patient_id)
    if not patient or patient.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Patient not found")

    entry = grant_consent(
        db=db,
        patient_id=patient_id,
        consent_type=body.get("consent_type", "appointment"),
        channel=body.get("channel", "admin"),
        consent_text=body.get("consent_text", ""),
        tenant_id=tenant.id,
        ip_address=request.client.host if request else None,
    )

    patient.consent_status = "granted"
    patient.consent_timestamp = datetime.utcnow()
    patient.consent_channel = "admin"

    record_audit_event(
        db=db,
        tenant_id=tenant.id,
        action="consent_granted",
        actor_type="staff",
        actor_id=f"admin/{tenant.id}",
        patient_id=patient_id,
        resource_type="consent",
        resource_id=str(entry.id),
        ip_address=request.client.host if request else None,
    )

    return {"ok": True, "consent_id": str(entry.id)}


@router.post("/api/compliance/patients/{patient_id}/consent/revoke")
def api_revoke_consent(
    patient_id: UUID,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    request: Request = None,
):
    patient = db.get(Patient, patient_id)
    if not patient or patient.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Patient not found")

    revoked = revoke_consent(db, patient_id, "appointment", tenant.id)
    if not revoked:
        raise HTTPException(status_code=400, detail="No active consent to revoke")

    patient.consent_status = "revoked"

    record_audit_event(
        db=db,
        tenant_id=tenant.id,
        action="consent_revoked",
        actor_type="staff",
        actor_id=f"admin/{tenant.id}",
        patient_id=patient_id,
        resource_type="consent",
        resource_id=str(revoked.id),
        ip_address=request.client.host if request else None,
    )

    return {"ok": True, "consent_id": str(revoked.id)}


@router.get("/api/compliance/audit-logs")
def api_list_audit_logs(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    action: str | None = Query(None),
    patient_id: UUID | None = Query(None),
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    query = select(AuditLog).where(AuditLog.tenant_id == tenant.id)
    count_query = select(func.count(AuditLog.id)).where(AuditLog.tenant_id == tenant.id)

    if action:
        query = query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)
    if patient_id:
        query = query.where(AuditLog.patient_id == patient_id)
        count_query = count_query.where(AuditLog.patient_id == patient_id)
    if from_date:
        query = query.where(AuditLog.timestamp >= from_date)
        count_query = count_query.where(AuditLog.timestamp >= from_date)
    if to_date:
        query = query.where(AuditLog.timestamp <= to_date)
        count_query = count_query.where(AuditLog.timestamp <= to_date)

    total = db.execute(count_query).scalar() or 0

    logs = db.execute(
        query.order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit)
    ).scalars().all()

    sanitized = []
    for log in logs:
        entry = {
            "id": str(log.id),
            "action": log.action,
            "actor_type": log.actor_type,
            "actor_id": log.actor_id,
            "patient_id": str(log.patient_id) if log.patient_id else None,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "details": strip_phi(str(log.details or {})),
            "ip_address": log.ip_address,
            "timestamp": log.timestamp.isoformat(),
            "retention_until": log.retention_until.isoformat() if log.retention_until else None,
        }
        sanitized.append(entry)

    return {"items": sanitized, "total": total, "limit": limit, "offset": offset}


@router.get("/api/compliance/audit/export")
def api_export_audit_logs(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
):
    csv_content = AuditLogger.export(db, tenant.id, from_date=from_date, to_date=to_date)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
    )


@router.post("/api/compliance/retention/apply")
def api_apply_retention(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    result = apply_retention_policy(db, str(tenant.id))
    return {"ok": True, **result}


@router.get("/api/compliance/retention/settings")
def api_get_retention_settings(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    from ..core.compliance.retention import _get_retention_config
    return {"settings": _get_retention_config()}


@router.put("/api/compliance/retention/settings")
def api_update_retention_settings(
    body: dict,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    return {"ok": True, "message": "Retention settings saved (in-memory only — update config.yaml for persistence)"}


@router.post("/api/compliance/retention/purge")
def api_purge_expired(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    count = RetentionPolicy.delete_expired(db, tenant.id)
    return {"ok": True, "deleted": count}


@router.get("/api/compliance/summary")
def api_compliance_summary(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    total_patients = db.execute(
        select(func.count(Patient.id)).where(Patient.tenant_id == tenant.id)
    ).scalar() or 0

    consented = db.execute(
        select(func.count(Patient.id)).where(
            Patient.tenant_id == tenant.id, Patient.consent_status == "granted"
        )
    ).scalar() or 0

    recent_audit = db.execute(
        select(func.count(AuditLog.id)).where(
            AuditLog.tenant_id == tenant.id,
            AuditLog.timestamp >= datetime.utcnow(),
        )
    ).scalar() or 0

    return {
        "total_patients": total_patients,
        "patients_with_consent": consented,
        "consent_rate": round(consented / total_patients * 100, 1) if total_patients else 0.0,
        "audit_events_today": recent_audit,
    }
