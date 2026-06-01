from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from ...config import get_yaml_config
from ...models import Provider


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
    from ...models import CrmConnection

    # 1. Try CRM
    conn = db.query(CrmConnection).filter(
        CrmConnection.tenant_id == tenant_id,
        CrmConnection.status == "connected",
    ).first()
    if conn:
        from ...integrations.crm import get_crm_adapter
        adapter = get_crm_adapter(conn.provider, conn.config)
        target_date = (day or date.today()).isoformat()
        crm_slots = adapter.search_available_slots(
            doctor_id=provider_name or "",
            date=target_date,
        )
        if isinstance(crm_slots, list):
            return [
                Slot(
                    start=datetime.fromisoformat(s.get("start_time", s.get("start", ""))) if s.get("start_time") or s.get("start") else datetime.utcnow(),
                    end=datetime.fromisoformat(s.get("end_time", s.get("end", ""))) if s.get("end_time") or s.get("end") else datetime.utcnow(),
                    provider_name=s.get("provider_name", provider_name or ""),
                    provider_specialty=s.get("provider_specialty"),
                    slot_token=s.get("slot_token", ""),
                )
                for s in crm_slots
            ][:limit]

    # 2. Try Calendar provider
    from ..calendar import get_calendar_provider

    calendar = get_calendar_provider(tenant_id, db)
    if calendar:
        import asyncio

        target_date = (day or date.today()).isoformat()
        cfg = get_yaml_config()
        booking_cfg = cfg.get("booking", {})
        slot_duration = booking_cfg.get("slot_duration_minutes", 30)
        buffer_minutes = booking_cfg.get("buffer_minutes", 5)
        hours_start = booking_cfg.get("default_start_hour", 9)
        hours_end = booking_cfg.get("default_end_hour", 17)

        calendar_id = provider_name or "primary"
        cal_slots = asyncio.run(calendar.get_available_slots(
            calendar_id=calendar_id,
            date_str=target_date,
            slot_duration_minutes=slot_duration,
            buffer_minutes=buffer_minutes,
            working_hours_start=f"{hours_start:02d}:00",
            working_hours_end=f"{hours_end:02d}:00",
        ))
        return cal_slots[:limit]

    return []
