from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from .slot_manager import get_available_slots, generate_slots, Slot
from .scheduler import SlotAlreadyBookedError, AppointmentNotFoundError


def _get_pabau_adapter(tenant_id: UUID, db: Session):
    from ...models import Tenant
    tenant = db.get(Tenant, tenant_id)
    if not tenant or not tenant.pabau_config:
        return None
    from ...integrations.pabau import PabauConnector
    return PabauConnector(tenant.pabau_config)


def book_appointment(
    db: Session,
    tenant_id: UUID,
    patient_id: UUID,
    slot_token: str,
    provider_name: str,
    start_time: datetime,
    end_time: datetime,
    reason: str | None = None,
    source: str = "whatsapp",
):
    from ...models import AppointmentCache

    adapter = _get_pabau_adapter(tenant_id, db)
    if not adapter:
        raise RuntimeError("Pabau is not configured. Set up Pabau integration first.")

    crm_result = adapter.create_appointment(
        patient_id=str(patient_id),
        data={
            "provider_name": provider_name,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "reason": reason,
            "source": source,
        },
    )
    cache = AppointmentCache(
        tenant_id=tenant_id,
        patient_id=patient_id,
        external_id=str(crm_result.get("id", "")),
        status="scheduled",
        slot_token=slot_token,
        source=source,
    )
    db.add(cache)
    db.flush()
    return cache


def cancel_appointment(
    db: Session,
    appointment_id: UUID,
    reason: str | None = None,
) -> bool:
    from ...models import AppointmentCache

    cache = db.get(AppointmentCache, appointment_id)
    if not cache:
        return False

    adapter = _get_pabau_adapter(cache.tenant_id, db)
    if adapter and cache.external_id:
        adapter.cancel_appointment(cache.external_id)
        cache.status = "cancelled"
        db.flush()
        return True

    return False


def reschedule_appointment(
    db: Session,
    appointment_id: UUID,
    new_slot_token: str,
    new_start: datetime,
    new_end: datetime,
    new_provider_name: str | None = None,
):
    from ...models import AppointmentCache

    cache = db.get(AppointmentCache, appointment_id)
    if not cache:
        raise AppointmentNotFoundError(f"Appointment {appointment_id} not found")

    adapter = _get_pabau_adapter(cache.tenant_id, db)
    if adapter and cache.external_id:
        adapter.update_appointment(cache.external_id, {
            "start_time": new_start.isoformat(),
            "end_time": new_end.isoformat(),
            "provider_name": new_provider_name or "",
            "status": "scheduled",
        })
        cache.status = "scheduled"
        db.flush()
        return cache

    raise RuntimeError("Pabau is not configured. Set up Pabau integration first.")


__all__ = [
    "Slot",
    "get_available_slots",
    "generate_slots",
    "book_appointment",
    "reschedule_appointment",
    "cancel_appointment",
    "SlotAlreadyBookedError",
    "AppointmentNotFoundError",
]
