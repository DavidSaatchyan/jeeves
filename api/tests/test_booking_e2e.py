"""End-to-end tests for the booking/appointment flow (Calendar/CRM passthrough)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.models import AppointmentCache, CrmConnection, Provider, Tenant
from app.core.booking import (
    Slot,
    get_available_slots,
    generate_slots,
    book_appointment,
    reschedule_appointment,
    cancel_appointment,
    SlotAlreadyBookedError,
    AppointmentNotFoundError,
)
from app.core.calendar import CalendarProviderError

REF_DATE = date(2026, 6, 1)
REF_DT = datetime(2026, 6, 1, 9, 0, 0)


@pytest.fixture
def mock_db():
    m = MagicMock(spec=Session)
    crm_query = MagicMock()
    crm_query.filter.return_value.first.return_value = None
    m.query.return_value = crm_query
    m.get.return_value = None
    return m


@pytest.fixture
def mock_crm_conn(mock_db: MagicMock, tenant_id: UUID) -> CrmConnection:
    conn = MagicMock(spec=CrmConnection)
    conn.provider = "zoho"
    conn.status = "connected"
    conn.config = {}
    crm_query = MagicMock()
    crm_query.filter.return_value.first.return_value = conn
    mock_db.query.return_value = crm_query
    return conn


@pytest.fixture
def sample_provider(tenant_id: UUID) -> Provider:
    p = MagicMock(spec=Provider)
    p.id = uuid4()
    p.name = "Dr. Smith"
    p.specialty = "Cardiology"
    p.schedule = {
        "monday": [{"start": "09:00", "end": "12:00"}, {"start": "13:00", "end": "17:00"}],
    }
    p.tenant_id = tenant_id
    return p


@pytest.fixture
def sample_cache(tenant_id: UUID) -> AppointmentCache:
    c = MagicMock(spec=AppointmentCache)
    c.id = uuid4()
    c.tenant_id = tenant_id
    c.patient_id = uuid4()
    c.external_id = "crm_evt_001"
    c.status = "scheduled"
    c.slot_token = "token_123"
    c.source = "whatsapp"
    return c


# ── Slot Generation ───────────────────────────────────────────────────────

class TestSlotGeneration:
    def test_generate_slots_from_schedule(self, sample_provider: Provider):
        slots = generate_slots(sample_provider, REF_DATE, [])
        assert len(slots) > 0
        for s in slots:
            assert isinstance(s, Slot)
            assert s.provider_name == "Dr. Smith"
            assert s.start.date() == REF_DATE
            assert s.end > s.start
            assert len(s.slot_token) > 0

    def test_generate_slots_skips_booked(self, sample_provider: Provider):
        booked_start = REF_DT + timedelta(hours=9, minutes=30)
        booked_end = booked_start + timedelta(minutes=30)
        slots = generate_slots(sample_provider, REF_DATE, [(booked_start, booked_end)])
        for s in slots:
            assert not (s.start < booked_end and s.end > booked_start)

    def test_generate_slots_no_schedule_uses_defaults(self, sample_provider: Provider):
        sample_provider.schedule = {}
        with patch("app.core.booking.slot_manager.get_yaml_config") as mock_cfg:
            mock_cfg.return_value = {"booking": {"default_start_hour": 9, "default_end_hour": 17}}
            slots = generate_slots(sample_provider, REF_DATE, [])
            assert len(slots) > 0

    def test_generate_slots_all_booked_returns_empty(self, sample_provider: Provider):
        day_long = [(REF_DT.replace(hour=0, minute=0), REF_DT.replace(hour=0, minute=0) + timedelta(hours=24))]
        slots = generate_slots(sample_provider, REF_DATE, day_long)
        assert len(slots) == 0

    def test_generate_slots_token_unique(self, sample_provider: Provider):
        slots = generate_slots(sample_provider, REF_DATE, [])
        tokens = [s.slot_token for s in slots]
        assert len(tokens) == len(set(tokens))


# ── Get Available Slots ───────────────────────────────────────────────────

class TestGetAvailableSlots:
    def test_no_backend_returns_empty(self, mock_db: MagicMock, tenant_id: UUID):
        slots = get_available_slots(mock_db, tenant_id, day=REF_DATE)
        assert slots == []

    def test_with_crm_adapter(self, mock_db: MagicMock, mock_crm_conn: CrmConnection, tenant_id: UUID):
        with patch("app.integrations.crm.get_crm_adapter") as mock_adapter:
            adapter = MagicMock()
            adapter.search_available_slots.return_value = [
                {"start_time": "2026-06-01T09:00:00", "end_time": "2026-06-01T09:30:00", "provider_name": "Dr. Smith"},
            ]
            mock_adapter.return_value = adapter
            slots = get_available_slots(mock_db, tenant_id, day=REF_DATE)
            assert len(slots) == 1
            assert slots[0].provider_name == "Dr. Smith"

    def test_with_calendar_provider(self, mock_db: MagicMock, tenant_id: UUID):
        expected = [
            Slot(start=REF_DT, end=REF_DT + timedelta(minutes=30), provider_name="primary", provider_specialty=None, slot_token="tok1"),
        ]
        async def mock_async(*args, **kwargs):
            return expected
        mock_cal = MagicMock()
        mock_cal.get_available_slots = mock_async
        with patch("app.core.calendar.get_calendar_provider") as mock_get_cal:
            mock_get_cal.return_value = mock_cal
            slots = get_available_slots(mock_db, tenant_id, day=REF_DATE)
            assert len(slots) == 1


# ── Book Appointment ──────────────────────────────────────────────────────

class TestBookAppointment:
    def test_with_crm_adapter(self, mock_db: MagicMock, mock_crm_conn: CrmConnection, tenant_id: UUID):
        with patch("app.integrations.crm.get_crm_adapter") as mock_adapter:
            adapter = MagicMock()
            adapter.create_appointment.return_value = {"id": "crm_001"}
            mock_adapter.return_value = adapter
            result = book_appointment(
                db=mock_db, tenant_id=tenant_id, patient_id=uuid4(),
                slot_token="tok1", provider_name="Dr. Smith",
                start_time=REF_DT, end_time=REF_DT + timedelta(minutes=30),
            )
            assert isinstance(result, AppointmentCache)
            assert result.external_id == "crm_001"
            mock_db.add.assert_called_once()
            mock_db.flush.assert_called_once()

    def test_with_calendar_provider(self, mock_db: MagicMock, tenant_id: UUID):
        with (
            patch("app.core.booking.get_calendar_provider") as mock_get_cal,
            patch("asyncio.run") as mock_run,
        ):
            mock_cal = MagicMock()
            event = MagicMock()
            event.external_id = "gcal_001"
            mock_cal.create_event.return_value = event
            mock_get_cal.return_value = mock_cal
            mock_run.return_value = event
            result = book_appointment(
                db=mock_db, tenant_id=tenant_id, patient_id=uuid4(),
                slot_token="tok1", provider_name="Dr. Smith",
                start_time=REF_DT, end_time=REF_DT + timedelta(minutes=30),
            )
            assert isinstance(result, AppointmentCache)
            assert result.external_id == "gcal_001"

    def test_without_backend_raises_error(self, mock_db: MagicMock, tenant_id: UUID):
        with pytest.raises(CalendarProviderError):
            book_appointment(
                db=mock_db, tenant_id=tenant_id, patient_id=uuid4(),
                slot_token="tok1", provider_name="Dr. Smith",
                start_time=REF_DT, end_time=REF_DT + timedelta(minutes=30),
            )


# ── Cancel Appointment ────────────────────────────────────────────────────

class TestCancelAppointment:
    def test_with_crm_adapter(self, mock_db: MagicMock, mock_crm_conn: CrmConnection, tenant_id: UUID, sample_cache: AppointmentCache):
        mock_db.get.return_value = sample_cache
        with patch("app.integrations.crm.get_crm_adapter") as mock_adapter:
            adapter = MagicMock()
            mock_adapter.return_value = adapter
            result = cancel_appointment(mock_db, sample_cache.id)
            assert result is True
            assert sample_cache.status == "cancelled"

    def test_with_calendar_provider(self, mock_db: MagicMock, tenant_id: UUID, sample_cache: AppointmentCache):
        mock_db.get.return_value = sample_cache
        with (
            patch("app.core.booking.get_calendar_provider") as mock_get_cal,
            patch("asyncio.run") as mock_run,
        ):
            mock_cal = MagicMock()
            mock_cal.cancel_event.return_value = True
            mock_get_cal.return_value = mock_cal
            mock_run.return_value = True
            result = cancel_appointment(mock_db, sample_cache.id)
            assert result is True

    def test_not_found_returns_false(self, mock_db: MagicMock, tenant_id: UUID):
        mock_db.get.return_value = None
        result = cancel_appointment(mock_db, uuid4())
        assert result is False


# ── Reschedule Appointment ────────────────────────────────────────────────

class TestRescheduleAppointment:
    def test_with_crm_adapter(self, mock_db: MagicMock, mock_crm_conn: CrmConnection, tenant_id: UUID, sample_cache: AppointmentCache):
        mock_db.get.return_value = sample_cache
        with patch("app.integrations.crm.get_crm_adapter") as mock_adapter:
            adapter = MagicMock()
            mock_adapter.return_value = adapter
            new_start = REF_DT + timedelta(hours=2)
            new_end = new_start + timedelta(minutes=30)
            result = reschedule_appointment(mock_db, sample_cache.id, "tok2", new_start, new_end)
            assert result is not None
            adapter.update_appointment.assert_called_once()

    def test_with_calendar_provider(self, mock_db: MagicMock, tenant_id: UUID, sample_cache: AppointmentCache):
        mock_db.get.return_value = sample_cache
        with (
            patch("app.core.booking.get_calendar_provider") as mock_get_cal,
            patch("asyncio.run") as mock_run,
        ):
            mock_cal = MagicMock()
            event = MagicMock()
            mock_cal.update_event.return_value = event
            mock_get_cal.return_value = mock_cal
            mock_run.return_value = event
            new_start = REF_DT + timedelta(hours=2)
            new_end = new_start + timedelta(minutes=30)
            result = reschedule_appointment(mock_db, sample_cache.id, "tok2", new_start, new_end)
            assert result is not None

    def test_not_found_raises_error(self, mock_db: MagicMock, tenant_id: UUID):
        mock_db.get.return_value = None
        with pytest.raises(AppointmentNotFoundError):
            reschedule_appointment(mock_db, uuid4(), "tok2", REF_DT, REF_DT + timedelta(minutes=30))


# ── Error Types ───────────────────────────────────────────────────────────

class TestErrorTypes:
    def test_slot_already_booked_error(self):
        err = SlotAlreadyBookedError("test")
        assert isinstance(err, Exception)
        assert str(err) == "test"

    def test_appointment_not_found_error(self):
        err = AppointmentNotFoundError("test")
        assert isinstance(err, Exception)
        assert str(err) == "test"

    def test_calendar_provider_error(self):
        err = CalendarProviderError("test")
        assert isinstance(err, Exception)
        assert str(err) == "test"
