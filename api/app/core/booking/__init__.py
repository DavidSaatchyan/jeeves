from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from .slot_manager import get_available_slots, generate_slots, Slot
from .scheduler import (
    book_appointment as _local_book,
    reschedule_appointment as _local_reschedule,
    cancel_appointment as _local_cancel,
    get_conflicts,
    SlotAlreadyBookedError,
    AppointmentNotFoundError,
)
from .calendar_sync import push_to_calendar, pull_from_calendar, sync_calendar


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
    from ...models import AppointmentCache, CrmConnection

    conn = db.query(CrmConnection).filter(
        CrmConnection.tenant_id == tenant_id,
        CrmConnection.status == "connected",
    ).first()
    if conn:
        from ...integrations.crm import get_crm_adapter
        adapter = get_crm_adapter(conn.provider, conn.config)
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
    return _local_book(db, tenant_id, patient_id, slot_token, provider_name, start_time, end_time, reason, source)


def cancel_appointment(
    db: Session,
    appointment_id: UUID,
    reason: str | None = None,
) -> bool:
    from ...models import AppointmentCache, CrmConnection

    cache = db.get(AppointmentCache, appointment_id)
    if cache:
        conn = db.query(CrmConnection).filter(
            CrmConnection.tenant_id == cache.tenant_id,
            CrmConnection.status == "connected",
        ).first()
        if conn and cache.external_id:
            from ...integrations.crm import get_crm_adapter
            adapter = get_crm_adapter(conn.provider, conn.config)
            adapter.cancel_appointment(cache.external_id)
            cache.status = "cancelled"
            db.flush()
            return True
    return _local_cancel(db, appointment_id, reason)


def reschedule_appointment(
    db: Session,
    appointment_id: UUID,
    new_slot_token: str,
    new_start: datetime,
    new_end: datetime,
    new_provider_name: str | None = None,
):
    from ...models import AppointmentCache, CrmConnection

    cache = db.get(AppointmentCache, appointment_id)
    if cache:
        conn = db.query(CrmConnection).filter(
            CrmConnection.tenant_id == cache.tenant_id,
            CrmConnection.status == "connected",
        ).first()
        if conn and cache.external_id:
            from ...integrations.crm import get_crm_adapter
            adapter = get_crm_adapter(conn.provider, conn.config)
            adapter.update_appointment(cache.external_id, {
                "start_time": new_start.isoformat(),
                "end_time": new_end.isoformat(),
                "provider_name": new_provider_name or "",
                "status": "scheduled",
            })
            cache.status = "scheduled"
            db.flush()
            return cache
    return _local_reschedule(db, appointment_id, new_slot_token, new_start, new_end, new_provider_name)


__all__ = [
    "Slot",
    "get_available_slots",
    "generate_slots",
    "book_appointment",
    "reschedule_appointment",
    "cancel_appointment",
    "get_conflicts",
    "SlotAlreadyBookedError",
    "AppointmentNotFoundError",
    "push_to_calendar",
    "pull_from_calendar",
    "sync_calendar",
]
