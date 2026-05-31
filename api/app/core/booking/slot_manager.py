from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import get_yaml_config
from ...models import Appointment, Provider


@dataclass
class Slot:
    start: datetime
    end: datetime
    provider_name: str
    provider_specialty: str | None
    slot_token: str


def generate_slots(
    provider: Provider,
    day: date,
    booked: list[tuple[datetime, datetime]],
    slot_duration: int = 30,
    buffer_minutes: int = 5,
) -> list[Slot]:
    schedule: dict = provider.schedule or {}
    day_name = day.strftime("%A").lower()
    blocks = schedule.get(day_name)
    if not blocks:
        return _default_slots(provider, day, booked, slot_duration, buffer_minutes)

    results: list[Slot] = []
    for block in blocks:
        start_str = block.get("start", "09:00")
        end_str = block.get("end", "17:00")
        block_start = datetime.combine(day, time.fromisoformat(start_str))
        block_end = datetime.combine(day, time.fromisoformat(end_str))
        cursor = block_start
        while cursor + timedelta(minutes=slot_duration) <= block_end:
            slot_start = cursor
            slot_end = cursor + timedelta(minutes=slot_duration)
            if not _overlaps(slot_start, slot_end, booked):
                results.append(Slot(
                    start=slot_start,
                    end=slot_end,
                    provider_name=provider.name,
                    provider_specialty=provider.specialty,
                    slot_token=secrets.token_hex(16),
                ))
            cursor += timedelta(minutes=slot_duration + buffer_minutes)

    return results


def _default_slots(
    provider: Provider,
    day: date,
    booked: list[tuple[datetime, datetime]],
    slot_duration: int,
    buffer_minutes: int,
) -> list[Slot]:
    cfg = get_yaml_config()
    booking_cfg = cfg.get("booking", {})
    start_hour = booking_cfg.get("default_start_hour", 9)
    end_hour = booking_cfg.get("default_end_hour", 17)
    block_start = datetime.combine(day, time(start_hour, 0))
    block_end = datetime.combine(day, time(end_hour, 0))
    results: list[Slot] = []
    cursor = block_start
    while cursor + timedelta(minutes=slot_duration) <= block_end:
        slot_start = cursor
        slot_end = cursor + timedelta(minutes=slot_duration)
        if not _overlaps(slot_start, slot_end, booked):
            results.append(Slot(
                start=slot_start,
                end=slot_end,
                provider_name=provider.name,
                provider_specialty=provider.specialty,
                slot_token=secrets.token_hex(16),
            ))
        cursor += timedelta(minutes=slot_duration + buffer_minutes)
    return results


def _overlaps(start: datetime, end: datetime, booked: list[tuple[datetime, datetime]]) -> bool:
    for bs, be in booked:
        if start < be and end > bs:
            return True
    return False


def get_available_slots(
    db: Session,
    tenant_id: UUID,
    provider_name: str | None = None,
    specialty: str | None = None,
    day: date | None = None,
    limit: int = 10,
) -> list[Slot]:
    cfg = get_yaml_config()
    booking_cfg = cfg.get("booking", {})
    slot_duration = booking_cfg.get("slot_duration_minutes", 30)
    buffer_minutes = booking_cfg.get("buffer_minutes", 5)

    query = select(Provider).where(
        Provider.tenant_id == tenant_id,
    )
    if provider_name:
        query = query.where(Provider.name == provider_name)
    if specialty:
        query = query.where(Provider.specialty == specialty)
    providers = db.execute(query).scalars().all()

    target_day = day or date.today()
    all_slots: list[Slot] = []

    booked_map: dict[str, list[tuple[datetime, datetime]]] = {}

    for prov in providers:
        appt_rows = db.execute(
            select(Appointment).where(
                Appointment.tenant_id == tenant_id,
                Appointment.provider_name == prov.name,
                Appointment.status.in_(["scheduled", "confirmed", "arrived", "in_progress"]),
            )
        ).scalars().all()

        booked_map[prov.name] = [
            (a.start_time, a.end_time) for a in appt_rows
            if a.start_time.date() == target_day
        ]

        slots = generate_slots(prov, target_day, booked_map[prov.name], slot_duration, buffer_minutes)
        all_slots.extend(slots)

    all_slots.sort(key=lambda s: s.start)
    return all_slots[:limit]
