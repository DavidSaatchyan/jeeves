from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .exceptions import ConnectorError
from .resolver import get_crm_adapter_for_tenant
from ..db import get_db
from ..models import AppointmentCache, AuditLog, Patient, Tenant

logger = logging.getLogger("jeeves.webhooks")

router = APIRouter(prefix="/integrations/webhooks", tags=["webhooks"])


def _get_tenant(db: Session, tenant_id: uuid.UUID | str) -> Tenant | None:
    if isinstance(tenant_id, str):
        tenant_id = uuid.UUID(tenant_id)
    return db.get(Tenant, tenant_id)


def _verify(payload: bytes, signature: str, config: dict[str, Any]) -> bool:
    secret = config.get("webhook_secret", "")
    if not secret:
        return True
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _upsert_patient(db: Session, tenant_id: uuid.UUID, data: dict[str, Any]) -> Patient:
    external_id = str(data.get("id", ""))
    if not external_id:
        raise HTTPException(status_code=400, detail="Patient external_id required")

    patient = db.query(Patient).filter(
        Patient.tenant_id == tenant_id,
        Patient.external_id == external_id,
    ).first()

    if patient:
        for field in ("first_name", "last_name", "email", "phone"):
            if data.get(field):
                setattr(patient, field, data[field])
        patient.updated_at = datetime.utcnow()
    else:
        patient = Patient(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            external_id=external_id,
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            email=data.get("email"),
            phone=data.get("phone", ""),
        )
        db.add(patient)

    db.flush()
    return patient


def _sync_appointment(db: Session, tenant_id: uuid.UUID, patient_id: uuid.UUID, data: dict[str, Any]) -> AppointmentCache:
    external_id = str(data.get("id", ""))
    cache = None
    if external_id:
        cache = db.query(AppointmentCache).filter(
            AppointmentCache.tenant_id == tenant_id,
            AppointmentCache.external_id == external_id,
        ).first()

    if cache:
        cache.status = data.get("status", cache.status)
        cache.last_synced_at = datetime.utcnow()
        cache.updated_at = datetime.utcnow()
    else:
        cache = AppointmentCache(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            patient_id=patient_id,
            external_id=external_id,
            status=data.get("status", "scheduled"),
            cached_at=datetime.utcnow(),
            last_synced_at=datetime.utcnow(),
        )
        db.add(cache)

    db.flush()
    return cache


def _log_audit(db: Session, tenant_id: uuid.UUID, patient_id: uuid.UUID | None, action: str, resource_type: str, resource_id: str, source: str = "webhook") -> None:
    entry = AuditLog(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        patient_id=patient_id,
        actor_type="system",
        actor_id=f"webhook/{source}",
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details={"source": f"{source}_webhook"},
        timestamp=datetime.utcnow(),
    )
    db.add(entry)
    db.flush()


async def _process_webhook(
    tenant_id: str,
    request: Request,
    db: Session,
    source: str,
    sig_headers: list[str],
) -> dict:
    tenant = _get_tenant(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    config = dict(tenant.crm_config or {})
    payload_bytes = await request.body()
    signature = ""
    for hdr in sig_headers:
        signature = request.headers.get(hdr, "")
        if signature:
            break

    if not _verify(payload_bytes, signature, config):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload_data = json.loads(payload_bytes)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    adapter = get_crm_adapter_for_tenant(tenant)
    if not adapter:
        raise HTTPException(status_code=502, detail="CRM adapter not available")

    try:
        event = adapter.parse_webhook_event(payload_data)
    except ConnectorError as e:
        raise HTTPException(status_code=400, detail=str(e))

    event_type = event.get("event", "unknown")
    resource = event.get("resource", {})

    if "patient" in event_type.lower() or "contact" in event_type.lower():
        patient = _upsert_patient(db, tenant.id, resource)
        _log_audit(db, tenant.id, patient.id, f"{source}_{event_type}", "patient", str(patient.id), source)
        return {"ok": True, "entity": "patient", "id": str(patient.id)}

    if "appointment" in event_type.lower():
        patient_ext_id = str(resource.get("patient_id", ""))
        patient = db.query(Patient).filter(
            Patient.tenant_id == tenant.id,
            Patient.external_id == patient_ext_id,
        ).first()
        if not patient:
            raise HTTPException(status_code=404, detail="Linked patient not found")
        appt = _sync_appointment(db, tenant.id, patient.id, resource)
        _log_audit(db, tenant.id, patient.id, f"{source}_{event_type}", "appointment", str(appt.id), source)
        return {"ok": True, "entity": "appointment", "id": str(appt.id)}

    logger.info("%s webhook: unhandled event type %s", source, event_type)
    return {"ok": True, "event": event_type, "handled": False}


@router.post("/pabau/{tenant_id}")
async def pabau_webhook(tenant_id: str, request: Request, db: Session = Depends(get_db)):
    return await _process_webhook(tenant_id, request, db, "pabau", ["X-Webhook-Signature", "X-Pabau-Signature"])


@router.post("/cliniko/{tenant_id}")
async def cliniko_webhook(tenant_id: str, request: Request, db: Session = Depends(get_db)):
    return await _process_webhook(tenant_id, request, db, "cliniko", ["X-Cliniko-Signature", "X-Webhook-Signature"])
