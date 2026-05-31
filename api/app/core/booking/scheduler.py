from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Appointment


class SlotAlreadyBookedError(Exception):
    """Raised when the slot_token is already taken by another booking."""


class AppointmentNotFoundError(Exception):
    """Raised when appointment does not exist."""


def get_conflicts(
    db: Session,
    tenant_id: UUID,
    provider_name: str,
    start_time: datetime,
    end_time: datetime,
    exclude_appointment_id: UUID | None = None,
) -> list[Appointment]:
    query = select(Appointment).where(
        Appointment.tenant_id == tenant_id,
        Appointment.provider_name == provider_name,
        Appointment.status.in_(["scheduled", "confirmed", "arrived", "in_progress"]),
        Appointment.start_time < end_time,
        Appointment.end_time > start_time,
    )
    if exclude_appointment_id:
        query = query.where(Appointment.id != exclude_appointment_id)
    return list(db.execute(query).scalars().all())


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
) -> Appointment:
    # optimistic lock: check if slot_token is already taken
    existing = db.execute(
        select(Appointment).where(
            Appointment.slot_token == slot_token,
            Appointment.status.in_(["scheduled", "confirmed", "arrived", "in_progress"]),
        )
    ).first()
    if existing is not None:
        raise SlotAlreadyBookedError(f"Slot {slot_token} is already booked")

    # double-check time overlap
    conflicts = get_conflicts(db, tenant_id, provider_name, start_time, end_time)
    if conflicts:
        raise SlotAlreadyBookedError(f"Time slot {start_time}-{end_time} conflicts with existing appointment")

    appt = Appointment(
        id=uuid4(),
        tenant_id=tenant_id,
        patient_id=patient_id,
        provider_name=provider_name,
        start_time=start_time,
        end_time=end_time,
        status="scheduled",
        reason=reason,
        source=source,
        slot_token=slot_token,
    )
    db.add(appt)
    db.flush()
    return appt


def reschedule_appointment(
    db: Session,
    appointment_id: UUID,
    new_slot_token: str,
    new_start: datetime,
    new_end: datetime,
    new_provider_name: str | None = None,
) -> Appointment:
    appt = db.get(Appointment, appointment_id)
    if not appt:
        raise AppointmentNotFoundError(f"Appointment {appointment_id} not found")

    provider = new_provider_name or appt.provider_name

    # check new slot availability
    existing = db.execute(
        select(Appointment).where(
            Appointment.slot_token == new_slot_token,
            Appointment.status.in_(["scheduled", "confirmed", "arrived", "in_progress"]),
            Appointment.id != appointment_id,
        )
    ).first()
    if existing is not None:
        raise SlotAlreadyBookedError(f"New slot {new_slot_token} is already booked")

    appt.slot_token = new_slot_token
    appt.start_time = new_start
    appt.end_time = new_end
    if new_provider_name:
        appt.provider_name = new_provider_name
    appt.status = "scheduled"
    db.flush()
    return appt


def cancel_appointment(
    db: Session,
    appointment_id: UUID,
    reason: str | None = None,
) -> bool:
    appt = db.get(Appointment, appointment_id)
    if not appt:
        return False
    appt.status = "cancelled"
    if reason:
        appt.notes = (appt.notes or "") + f"\nCancellation reason: {reason}"
    db.flush()
    return True
