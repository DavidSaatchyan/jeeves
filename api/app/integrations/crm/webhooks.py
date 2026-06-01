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

from ...crypto import ConnectorError
from ...db import get_db
from ...models import AppointmentCache, AuditLog, CrmConnection, Patient

logger = logging.getLogger("jeeves.crm.webhooks")

router = APIRouter(prefix="/integrations/webhooks", tags=["crm-webhooks"])


def _get_connector(provider: str, db: Session, tenant_id: uuid.UUID | None = None) -> CrmConnection:
    q = db.query(CrmConnection).filter(CrmConnection.provider == provider)
    if tenant_id:
        q = q.filter(CrmConnection.tenant_id == tenant_id)
    conn = q.first()
    if not conn:
        raise HTTPException(status_code=404, detail=f"No {provider} connection configured")
    return conn


def _verify_signature(provider: str, payload: bytes, signature: str, config: dict[str, Any]) -> bool:
    """Verify webhook signature using the connector's configured secret."""
    from ..crm import get_crm_adapter
    try:
        adapter = get_crm_adapter(provider, config)
        return adapter.verify_webhook_signature(payload, signature)
    except ConnectorError:
        secret = config.get("webhook_secret", "")
        if not secret:
            logger.warning("webhook %s: no secret configured — skipping verification", provider)
            return True
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


def _upsert_patient(
    db: Session, tenant_id: uuid.UUID, data: dict[str, Any]
) -> Patient:
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


def _sync_appointment_from_webhook(
    db: Session, tenant_id: uuid.UUID, patient_id: uuid.UUID, data: dict[str, Any]
) -> AppointmentCache:
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


@router.post("/zoho")
async def webhook_zoho(request: Request, db: Session = Depends(get_db)):
    payload_bytes = await request.body()
    return _handle_webhook("zoho", payload_bytes, request, db)


@router.post("/hubspot")
async def webhook_hubspot(request: Request, db: Session = Depends(get_db)):
    payload_bytes = await request.body()
    return _handle_webhook("hubspot", payload_bytes, request, db)


@router.post("/custom/{tenant_id}")
async def webhook_custom(tenant_id: str, request: Request, db: Session = Depends(get_db)):
    payload_bytes = await request.body()
    return _handle_webhook("custom_api", payload_bytes, request, db, tenant_id=uuid.UUID(tenant_id))


def _handle_webhook(
    provider: str,
    payload_bytes: bytes,
    request: Request,
    db: Session,
    tenant_id: uuid.UUID | None = None,
):
    try:
        payload_data = json.loads(payload_bytes)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    signature = request.headers.get("X-Webhook-Signature", "")
    conn = _get_connector(provider, db, tenant_id)
    config = dict(conn.config or {})
    config["webhook_secret"] = conn.webhook_secret or ""

    if not _verify_signature(provider, payload_bytes, signature, config):
        logger.warning("webhook %s: signature mismatch", provider)
        raise HTTPException(status_code=401, detail="Invalid signature")

    from ..crm import get_crm_adapter
    try:
        adapter = get_crm_adapter(provider, config)
        event = adapter.parse_webhook_event(payload_data)
    except ConnectorError as e:
        logger.error("webhook %s: parse error: %s", provider, e)
        raise HTTPException(status_code=400, detail=str(e))

    event_type = event.get("event", "unknown")
    resource = event.get("resource", {})

    # PHI minimization for non-BAA providers
    if not adapter.phi_safe and resource:
        try:
            from ...core.compliance.phi_minimization import mask_phi
            resource = mask_phi(resource)
        except ImportError:
            pass

    # ── Handle patient events ───────────────────────────────────
    if "contact" in event_type.lower() or "patient" in event_type.lower():
        patient = _upsert_patient(db, conn.tenant_id, resource)
        _log_audit(db, conn.tenant_id, patient.id, f"crm_{provider}", f"{event_type}", "patient", str(patient.id))
        return {"ok": True, "entity": "patient", "id": str(patient.id)}

    # ── Handle appointment events ────────────────────────────────
    if "appointment" in event_type.lower():
        patient_ext_id = str(resource.get("patient_id", resource.get("Patient_ID", "")))
        patient = db.query(Patient).filter(
            Patient.tenant_id == conn.tenant_id,
            Patient.external_id == patient_ext_id,
        ).first()
        if not patient:
            raise HTTPException(status_code=404, detail="Linked patient not found. Sync patient first.")
        appt = _sync_appointment_from_webhook(db, conn.tenant_id, patient.id, resource)
        _log_audit(db, conn.tenant_id, patient.id, f"crm_{provider}", f"{event_type}", "appointment", str(appt.id))
        return {"ok": True, "entity": "appointment", "id": str(appt.id)}

    logger.info("webhook %s: unhandled event type %s", provider, event_type)
    return {"ok": True, "event": event_type, "handled": False}


def _log_audit(
    db: Session,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID | None,
    actor_type: str,
    action: str,
    resource_type: str,
    resource_id: str,
) -> None:
    entry = AuditLog(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        patient_id=patient_id,
        actor_type=actor_type,
        actor_id=f"webhook/{actor_type}",
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details={"source": "crm_webhook"},
        timestamp=datetime.utcnow(),
    )
    db.add(entry)
    db.flush()
