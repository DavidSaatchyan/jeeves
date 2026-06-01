from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from ..calendar import CalendarProviderError, get_calendar_provider
from .slot_manager import get_available_slots, generate_slots, Slot
from .scheduler import (
    SlotAlreadyBookedError,
    AppointmentNotFoundError,
)
from .calendar_sync import push_to_calendar, pull_from_calendar, sync_calendar


def _has_crm(tenant_id: UUID, db: Session) -> bool:
    from ...models import CrmConnection

    return db.query(CrmConnection).filter(
        CrmConnection.tenant_id == tenant_id,
        CrmConnection.status == "connected",
    ).first() is not None


def _get_crm_adapter(tenant_id: UUID, db: Session):
    from ...models import CrmConnection

    conn = db.query(CrmConnection).filter(
        CrmConnection.tenant_id == tenant_id,
        CrmConnection.status == "connected",
    ).first()
    if not conn:
        return None
    from ...integrations.crm import get_crm_adapter
    return get_crm_adapter(conn.provider, conn.config)


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

    # 1. Try CRM
    adapter = _get_crm_adapter(tenant_id, db)
    if adapter:
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

    # 2. Try Calendar provider
    calendar = get_calendar_provider(tenant_id, db)
    if calendar:
        import asyncio

        event = asyncio.run(calendar.create_event(
            calendar_id=provider_name,
            summary=reason or "Appointment",
            start=start_time,
            end=end_time,
            patient_id=str(patient_id),
            provider_name=provider_name,
        ))
        cache = AppointmentCache(
            tenant_id=tenant_id,
            patient_id=patient_id,
            external_id=event.external_id,
            status="scheduled",
            slot_token=slot_token,
            source=source,
        )
        db.add(cache)
        db.flush()
        return cache

    # 3. No backend configured
    raise CalendarProviderError(
        "No calendar backend configured. Connect Google Calendar or CRM."
    )


def cancel_appointment(
    db: Session,
    appointment_id: UUID,
    reason: str | None = None,
) -> bool:
    from ...models import AppointmentCache, CrmConnection

    cache = db.get(AppointmentCache, appointment_id)
    if not cache:
        return False

    conn = db.query(CrmConnection).filter(
        CrmConnection.tenant_id == cache.tenant_id,
        CrmConnection.status == "connected",
    ).first()

    if conn and cache.external_id:
        adapter = _get_crm_adapter(cache.tenant_id, db)
        if adapter:
            adapter.cancel_appointment(cache.external_id)
            cache.status = "cancelled"
            db.flush()
            return True

    calendar = get_calendar_provider(cache.tenant_id, db)
    if calendar and cache.external_id:
        import asyncio

        success = asyncio.run(calendar.cancel_event(
            calendar_id="primary",
            event_id=cache.external_id,
        ))
        if success:
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
    from ...models import AppointmentCache, CrmConnection

    cache = db.get(AppointmentCache, appointment_id)
    if not cache:
        raise AppointmentNotFoundError(f"Appointment {appointment_id} not found")

    conn = db.query(CrmConnection).filter(
        CrmConnection.tenant_id == cache.tenant_id,
        CrmConnection.status == "connected",
    ).first()

    if conn and cache.external_id:
        adapter = _get_crm_adapter(cache.tenant_id, db)
        if adapter:
            adapter.update_appointment(cache.external_id, {
                "start_time": new_start.isoformat(),
                "end_time": new_end.isoformat(),
                "provider_name": new_provider_name or "",
                "status": "scheduled",
            })
            cache.status = "scheduled"
            db.flush()
            return cache

    calendar = get_calendar_provider(cache.tenant_id, db)
    if calendar and cache.external_id:
        import asyncio

        asyncio.run(calendar.update_event(
            calendar_id="primary",
            event_id=cache.external_id,
            start=new_start,
            end=new_end,
            summary="Rescheduled appointment",
            status="scheduled",
        ))
        cache.status = "scheduled"
        db.flush()
        return cache

    raise CalendarProviderError(
        "No calendar backend configured. Connect Google Calendar or CRM."
    )


__all__ = [
    "Slot",
    "get_available_slots",
    "generate_slots",
    "book_appointment",
    "reschedule_appointment",
    "cancel_appointment",
    "SlotAlreadyBookedError",
    "AppointmentNotFoundError",
    "push_to_calendar",
    "pull_from_calendar",
    "sync_calendar",
]
