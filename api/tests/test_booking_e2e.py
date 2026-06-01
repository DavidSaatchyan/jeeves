"""End-to-end tests for the booking/appointment flow."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Appointment, AppointmentCache, Provider, Tenant
from app.core.booking import (
    Slot,
    get_available_slots,
    generate_slots,
    book_appointment,
    reschedule_appointment,
    cancel_appointment,
    get_conflicts,
    SlotAlreadyBookedError,
)
from app.core.booking.scheduler import AppointmentNotFoundError

REF_DATE = date(2026, 6, 1)
REF_DT = datetime(2026, 6, 1, 9, 0, 0)


@pytest.fixture
def mock_db():
    m = MagicMock(spec=Session)
    crm_query = MagicMock()
    crm_query.filter.return_value.first.return_value = None
    m.query.return_value = crm_query
    return m


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
def sample_appointment(tenant_id: UUID, sample_provider: Provider) -> Appointment:
    a = MagicMock(spec=Appointment)
    a.id = uuid4()
    a.tenant_id = tenant_id
    a.patient_id = uuid4()
    a.provider_name = sample_provider.name
    a.provider_specialty = sample_provider.specialty
    a.department = None
    a.start_time = REF_DT + timedelta(hours=1)
    a.end_time = REF_DT + timedelta(hours=1, minutes=30)
    a.status = "scheduled"
    a.reason = None
    a.notes = None
    a.source = "admin"
    a.slot_token = "token_123"
    a.external_id = None
    a.reminder_sent_24h = False
    a.reminder_sent_2h = False
    a.created_at = REF_DT
    a.updated_at = REF_DT
    return a


@pytest.fixture
def override_deps(app, mock_tenant: Tenant, mock_db: MagicMock):
    from app.admin.deps import get_admin_tenant
    from app.db import get_db

    app.dependency_overrides[get_admin_tenant] = lambda: mock_tenant
    app.dependency_overrides[get_db] = lambda: mock_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client(app, override_deps):
    with TestClient(app) as c:
        yield c


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

    def test_get_available_slots_returns_slots(self, mock_db: MagicMock, sample_provider: Provider, tenant_id: UUID):
        prov_result = MagicMock()
        prov_result.scalars.return_value.all.return_value = [sample_provider]
        appt_result = MagicMock()
        appt_result.scalars.return_value.all.return_value = []
        mock_db.execute.side_effect = [prov_result, appt_result]
        slots = get_available_slots(mock_db, tenant_id, day=REF_DATE)
        assert len(slots) > 0
        for s in slots:
            assert s.start.date() == REF_DATE

    def test_get_available_slots_filters_by_provider(self, mock_db: MagicMock, sample_provider: Provider, tenant_id: UUID):
        prov_result = MagicMock()
        prov_result.scalars.return_value.all.return_value = [sample_provider]
        appt_result = MagicMock()
        appt_result.scalars.return_value.all.return_value = []
        mock_db.execute.side_effect = [prov_result, appt_result]
        slots = get_available_slots(mock_db, tenant_id, provider_name="Dr. Smith", day=REF_DATE)
        assert all(s.provider_name == "Dr. Smith" for s in slots)

    def test_get_available_slots_filters_by_specialty(self, mock_db: MagicMock, sample_provider: Provider, tenant_id: UUID):
        prov_result = MagicMock()
        prov_result.scalars.return_value.all.return_value = [sample_provider]
        appt_result = MagicMock()
        appt_result.scalars.return_value.all.return_value = []
        mock_db.execute.side_effect = [prov_result, appt_result]
        slots = get_available_slots(mock_db, tenant_id, specialty="Cardiology", day=REF_DATE)
        assert all(s.provider_specialty == "Cardiology" for s in slots)

    def test_get_available_slots_respects_limit(self, mock_db: MagicMock, sample_provider: Provider, tenant_id: UUID):
        prov_result = MagicMock()
        prov_result.scalars.return_value.all.return_value = [sample_provider]
        appt_result = MagicMock()
        appt_result.scalars.return_value.all.return_value = []
        mock_db.execute.side_effect = [prov_result, appt_result]
        slots = get_available_slots(mock_db, tenant_id, day=REF_DATE, limit=3)
        assert len(slots) <= 3

    def test_get_available_slots_no_providers(self, mock_db: MagicMock, tenant_id: UUID):
        prov_result = MagicMock()
        prov_result.scalars.return_value.all.return_value = []
        appt_result = MagicMock()
        appt_result.scalars.return_value.all.return_value = []
        mock_db.execute.side_effect = [prov_result, appt_result]
        slots = get_available_slots(mock_db, tenant_id, day=REF_DATE)
        assert len(slots) == 0


class TestBooking:
    def test_book_success(self, mock_db: MagicMock, tenant_id: UUID):
        slot_result = MagicMock()
        slot_result.first.return_value = None
        conflict_result = MagicMock()
        conflict_result.scalars.return_value.all.return_value = []
        mock_db.execute.side_effect = [slot_result, conflict_result]
        patient_id = uuid4()
        appt = book_appointment(
            mock_db, tenant_id, patient_id, "token_abc", "Dr. Smith",
            REF_DT, REF_DT + timedelta(minutes=30), reason="Checkup",
        )
        assert isinstance(appt, Appointment)
        assert appt.status == "scheduled"
        assert appt.slot_token == "token_abc"
        assert appt.provider_name == "Dr. Smith"
        assert appt.patient_id == patient_id
        assert appt.tenant_id == tenant_id
        assert appt.reason == "Checkup"
        assert appt.source == "whatsapp"
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    def test_book_slot_already_taken(self, mock_db: MagicMock, tenant_id: UUID):
        existing = MagicMock()
        existing.first.return_value = MagicMock()
        mock_db.execute.return_value = existing
        with pytest.raises(SlotAlreadyBookedError):
            book_appointment(
                mock_db, tenant_id, uuid4(), "token_taken", "Dr. Smith",
                REF_DT, REF_DT + timedelta(minutes=30),
            )

    def test_book_time_conflict(self, mock_db: MagicMock, tenant_id: UUID):
        slot_result = MagicMock()
        slot_result.first.return_value = None
        conflict_result = MagicMock()
        conflict_result.scalars.return_value.all.return_value = [MagicMock(spec=Appointment)]
        mock_db.execute.side_effect = [slot_result, conflict_result]
        with pytest.raises(SlotAlreadyBookedError):
            book_appointment(
                mock_db, tenant_id, uuid4(), "token_abc", "Dr. Smith",
                REF_DT, REF_DT + timedelta(minutes=30),
            )

    def test_book_custom_source(self, mock_db: MagicMock, tenant_id: UUID):
        slot_result = MagicMock()
        slot_result.first.return_value = None
        conflict_result = MagicMock()
        conflict_result.scalars.return_value.all.return_value = []
        mock_db.execute.side_effect = [slot_result, conflict_result]
        appt = book_appointment(
            mock_db, tenant_id, uuid4(), "token_custom", "Dr. Smith",
            REF_DT, REF_DT + timedelta(minutes=30), source="widget",
        )
        assert appt.source == "widget"


class TestReschedule:
    def test_reschedule_success(self, mock_db: MagicMock, sample_appointment: Appointment):
        mock_db.get.return_value = sample_appointment
        slot_check = MagicMock()
        slot_check.first.return_value = None
        mock_db.execute.return_value = slot_check
        new_start = REF_DT + timedelta(hours=2)
        new_end = REF_DT + timedelta(hours=2, minutes=30)
        result = reschedule_appointment(mock_db, sample_appointment.id, "new_token_456", new_start, new_end)
        assert result.slot_token == "new_token_456"
        assert result.start_time == new_start
        assert result.end_time == new_end
        assert result.status == "scheduled"
        mock_db.flush.assert_called_once()

    def test_reschedule_not_found(self, mock_db: MagicMock):
        mock_db.get.return_value = None
        with pytest.raises(AppointmentNotFoundError):
            reschedule_appointment(mock_db, uuid4(), "token", REF_DT, REF_DT + timedelta(minutes=30))

    def test_reschedule_slot_taken(self, mock_db: MagicMock, sample_appointment: Appointment):
        mock_db.get.return_value = sample_appointment
        existing = MagicMock()
        existing.first.return_value = MagicMock()
        mock_db.execute.return_value = existing
        with pytest.raises(SlotAlreadyBookedError):
            reschedule_appointment(
                mock_db, sample_appointment.id, "taken_token",
                REF_DT + timedelta(hours=2), REF_DT + timedelta(hours=2, minutes=30),
            )

    def test_reschedule_new_provider(self, mock_db: MagicMock, sample_appointment: Appointment):
        mock_db.get.return_value = sample_appointment
        slot_check = MagicMock()
        slot_check.first.return_value = None
        mock_db.execute.return_value = slot_check
        result = reschedule_appointment(
            mock_db, sample_appointment.id, "prov_token",
            REF_DT + timedelta(hours=3), REF_DT + timedelta(hours=3, minutes=30),
            new_provider_name="Dr. Jones",
        )
        assert result.provider_name == "Dr. Jones"


class TestCancel:
    def test_cancel_success(self, mock_db: MagicMock, sample_appointment: Appointment):
        mock_db.get.return_value = sample_appointment
        result = cancel_appointment(mock_db, sample_appointment.id, reason="Patient request")
        assert result is True
        assert sample_appointment.status == "cancelled"
        mock_db.flush.assert_called_once()

    def test_cancel_not_found(self, mock_db: MagicMock):
        mock_db.get.return_value = None
        result = cancel_appointment(mock_db, uuid4())
        assert result is False

    def test_cancel_without_reason(self, mock_db: MagicMock, sample_appointment: Appointment):
        mock_db.get.return_value = sample_appointment
        result = cancel_appointment(mock_db, sample_appointment.id)
        assert result is True
        assert sample_appointment.status == "cancelled"


class TestConflicts:
    def test_get_conflicts_returns_overlapping(self, mock_db: MagicMock, tenant_id: UUID):
        overlapping = MagicMock(spec=Appointment)
        mock_db.execute.return_value.scalars.return_value.all.return_value = [overlapping]
        conflicts = get_conflicts(mock_db, tenant_id, "Dr. Smith", REF_DT, REF_DT + timedelta(hours=1))
        assert len(conflicts) == 1

    def test_get_conflicts_excludes_appointment(self, mock_db: MagicMock, tenant_id: UUID):
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        conflicts = get_conflicts(mock_db, tenant_id, "Dr. Smith", REF_DT, REF_DT + timedelta(hours=1), exclude_appointment_id=uuid4())
        assert len(conflicts) == 0

    def test_get_conflicts_no_overlap(self, mock_db: MagicMock, tenant_id: UUID):
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        conflicts = get_conflicts(mock_db, tenant_id, "Dr. Smith", REF_DT, REF_DT + timedelta(hours=1))
        assert len(conflicts) == 0


class TestAdminAPI:
    def test_list_slots(self, client: TestClient, mock_db: MagicMock, sample_provider: Provider, tenant_id: UUID):
        prov_result = MagicMock()
        prov_result.scalars.return_value.all.return_value = [sample_provider]
        appt_result = MagicMock()
        appt_result.scalars.return_value.all.return_value = []
        mock_db.execute.side_effect = [prov_result, appt_result]
        resp = client.get("/admin/api/appointments/slots?date=2026-06-01")
        assert resp.status_code == 200
        data = resp.json()
        assert "slots" in data
        if data["slots"]:
            slot = data["slots"][0]
            assert "slot_token" in slot
            assert "provider_name" in slot
            assert "start" in slot
            assert "end" in slot

    def test_create_appointment_success(self, client: TestClient, mock_db: MagicMock, tenant_id: UUID):
        slot_result = MagicMock()
        slot_result.first.return_value = None
        conflict_result = MagicMock()
        conflict_result.scalars.return_value.all.return_value = []
        mock_db.execute.side_effect = [slot_result, conflict_result]
        resp = client.post("/admin/api/appointments", json={
            "patient_id": str(uuid4()),
            "provider_name": "Dr. Smith",
            "start_time": "2026-06-01T09:00:00",
            "end_time": "2026-06-01T09:30:00",
            "reason": "Checkup",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "scheduled"
        assert data["provider_name"] == "Dr. Smith"
        assert "id" in data
        mock_db.commit.assert_called_once()

    def test_create_appointment_conflict(self, client: TestClient, mock_db: MagicMock):
        existing = MagicMock()
        existing.first.return_value = MagicMock()
        mock_db.execute.return_value = existing
        resp = client.post("/admin/api/appointments", json={
            "patient_id": str(uuid4()),
            "provider_name": "Dr. Smith",
            "start_time": "2026-06-01T09:00:00",
            "end_time": "2026-06-01T09:30:00",
        })
        assert resp.status_code == 409
        mock_db.rollback.assert_called_once()

    def test_list_appointments(self, client: TestClient, mock_db: MagicMock, sample_appointment: Appointment, tenant_id: UUID):
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = [sample_appointment]
        mock_db.execute.side_effect = [count_result, rows_result]
        resp = client.get("/admin/api/appointments")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["appointments"]) == 1
        assert data["appointments"][0]["provider_name"] == "Dr. Smith"

    def test_list_appointments_empty(self, client: TestClient, mock_db: MagicMock):
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []
        mock_db.execute.side_effect = [count_result, rows_result]
        resp = client.get("/admin/api/appointments")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert len(data["appointments"]) == 0

    def test_list_appointments_with_filters(self, client: TestClient, mock_db: MagicMock, sample_appointment: Appointment, tenant_id: UUID):
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = [sample_appointment]
        mock_db.execute.side_effect = [count_result, rows_result]
        resp = client.get(f"/admin/api/appointments?status=scheduled&provider=Dr.%20Smith&patient_id={sample_appointment.patient_id}")
        assert resp.status_code == 200
        assert len(resp.json()["appointments"]) == 1

    def test_get_appointment(self, client: TestClient, mock_db: MagicMock, sample_appointment: Appointment):
        result = MagicMock()
        result.scalar_one_or_none.return_value = sample_appointment
        mock_db.execute.return_value = result
        resp = client.get(f"/admin/api/appointments/{sample_appointment.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(sample_appointment.id)
        assert data["status"] == "scheduled"

    def test_get_appointment_not_found(self, client: TestClient, mock_db: MagicMock):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = result
        resp = client.get(f"/admin/api/appointments/{uuid4()}")
        assert resp.status_code == 404

    def test_update_appointment(self, client: TestClient, mock_db: MagicMock, sample_appointment: Appointment):
        result = MagicMock()
        result.scalar_one_or_none.return_value = sample_appointment
        mock_db.execute.return_value = result
        resp = client.patch(f"/admin/api/appointments/{sample_appointment.id}", json={
            "status": "confirmed",
            "notes": "Patient confirmed via phone",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == sample_appointment.status
        mock_db.commit.assert_called_once()

    def test_update_appointment_invalid_status(self, client: TestClient, mock_db: MagicMock, sample_appointment: Appointment):
        result = MagicMock()
        result.scalar_one_or_none.return_value = sample_appointment
        mock_db.execute.return_value = result
        resp = client.patch(f"/admin/api/appointments/{sample_appointment.id}", json={"status": "invalid_status"})
        assert resp.status_code == 422

    def test_update_appointment_not_found(self, client: TestClient, mock_db: MagicMock):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = result
        resp = client.patch(f"/admin/api/appointments/{uuid4()}", json={"status": "confirmed"})
        assert resp.status_code == 404

    def test_cancel_appointment(self, client: TestClient, mock_db: MagicMock, sample_appointment: Appointment):
        mock_db.get.return_value = sample_appointment
        resp = client.post(f"/admin/api/appointments/{sample_appointment.id}/cancel", json={"reason": "Patient request"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert sample_appointment.status == "cancelled"
        mock_db.commit.assert_called_once()

    def test_cancel_appointment_not_found(self, client: TestClient, mock_db: MagicMock):
        mock_db.get.return_value = None
        resp = client.post(f"/admin/api/appointments/{uuid4()}/cancel", json={})
        assert resp.status_code == 404

    def test_cancel_appointment_without_body(self, client: TestClient, mock_db: MagicMock, sample_appointment: Appointment):
        mock_db.get.return_value = sample_appointment
        resp = client.post(f"/admin/api/appointments/{sample_appointment.id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestCrmPassThrough:
    """CRM pass-through path in admin API (Phase B/C)."""

    def test_crm_pass_through_list_appointments(
        self, client: TestClient, mock_db: MagicMock,
    ):
        mock_adapter = MagicMock()
        mock_adapter.list_appointments.return_value = {
            "total": 2,
            "items": [
                {"id": "crm_1", "patient_id": str(uuid4()), "provider_name": "Dr. CRM",
                 "start_time": "2026-06-01T09:00", "end_time": "2026-06-01T09:30", "status": "scheduled"},
                {"id": "crm_2", "patient_id": str(uuid4()), "provider_name": "Dr. CRM",
                 "start_time": "2026-06-01T10:00", "end_time": "2026-06-01T10:30", "status": "scheduled"},
            ],
        }
        with patch("app.admin.appointments._get_crm_adapter", return_value=mock_adapter):
            resp = client.get("/admin/api/appointments")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert "appointments" in data
        assert len(data["appointments"]) == 2
        assert data["appointments"][0]["provider_name"] == "Dr. CRM"
        mock_adapter.list_appointments.assert_called_once()

    def test_crm_pass_through_get_appointment(
        self, client: TestClient, mock_db: MagicMock, tenant_id: UUID,
    ):
        cache_entry = MagicMock(spec=AppointmentCache)
        cache_entry.external_id = "crm_ext_1"
        cache_entry.tenant_id = tenant_id
        mock_db.execute.return_value.scalar_one_or_none.return_value = cache_entry

        mock_adapter = MagicMock()
        mock_adapter.get_appointment.return_value = {
            "id": "crm_ext_1",
            "external_id": "crm_ext_1",
            "patient_id": str(tenant_id),
            "provider_name": "Dr. CRM",
            "start_time": "2026-06-01T09:00",
            "end_time": "2026-06-01T09:30",
            "status": "scheduled",
        }
        with patch("app.admin.appointments._get_crm_adapter", return_value=mock_adapter):
            resp = client.get(f"/admin/api/appointments/{uuid4()}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["external_id"] == "crm_ext_1"
        assert data["provider_name"] == "Dr. CRM"

    def test_crm_pass_through_list_slots(
        self, client: TestClient, mock_db: MagicMock,
    ):
        mock_adapter = MagicMock()
        mock_adapter.search_available_slots.return_value = [
            {"start_time": "2026-06-01T09:00", "end_time": "2026-06-01T09:30",
             "provider_name": "Dr. CRM", "slot_token": "crm_slot_1"},
        ]
        with patch("app.admin.appointments._get_crm_adapter", return_value=mock_adapter):
            resp = client.get("/admin/api/appointments/slots?date=2026-06-01")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["slots"]) == 1
        assert data["slots"][0]["provider_name"] == "Dr. CRM"
        mock_adapter.search_available_slots.assert_called_once()

    def test_crm_pass_through_create_appointment(
        self, client: TestClient, mock_db: MagicMock,
    ):
        mock_adapter = MagicMock()
        mock_adapter.create_appointment.return_value = {
            "id": "crm_new_1",
            "patient_id": str(uuid4()),
            "provider_name": "Dr. CRM",
            "start_time": "2026-06-01T11:00",
            "end_time": "2026-06-01T11:30",
            "status": "scheduled",
        }
        with patch("app.admin.appointments._get_crm_adapter", return_value=mock_adapter):
            resp = client.post("/admin/api/appointments", json={
                "patient_id": str(uuid4()),
                "provider_name": "Dr. CRM",
                "start_time": "2026-06-01T11:00",
                "end_time": "2026-06-01T11:30",
                "reason": "CRM test",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "crm_new_1"
        assert data["provider_name"] == "Dr. CRM"
        mock_adapter.create_appointment.assert_called_once()

    def test_crm_pass_through_update_appointment(
        self, client: TestClient, mock_db: MagicMock,
    ):
        cache_entry = MagicMock(spec=AppointmentCache)
        cache_entry.id = uuid4()
        cache_entry.tenant_id = uuid4()
        cache_entry.external_id = "crm_ext_upd"
        cache_entry.status = "scheduled"
        cache_entry.patient_id = uuid4()
        cache_entry.source = "crm_sync"
        cache_entry.updated_at = datetime.utcnow()
        mock_db.get.return_value = cache_entry

        mock_adapter = MagicMock()
        with patch("app.admin.appointments._get_crm_adapter", return_value=mock_adapter):
            resp = client.patch(f"/admin/api/appointments/{cache_entry.id}", json={"status": "confirmed"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["external_id"] == "crm_ext_upd"
        assert data["status"] == "confirmed"
        mock_adapter.update_appointment.assert_called_once_with("crm_ext_upd", {"status": "confirmed"})
        assert cache_entry.status == "confirmed"

    def test_crm_pass_through_cancel_appointment(
        self, client: TestClient, mock_db: MagicMock,
    ):
        cache_entry = MagicMock(spec=AppointmentCache)
        cache_entry.id = uuid4()
        cache_entry.tenant_id = uuid4()
        cache_entry.external_id = "crm_ext_cancel"
        mock_db.get.return_value = cache_entry

        mock_adapter = MagicMock()
        with patch("app.admin.appointments._get_crm_adapter", return_value=mock_adapter):
            resp = client.post(f"/admin/api/appointments/{cache_entry.id}/cancel", json={"reason": "CRM test"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        mock_adapter.cancel_appointment.assert_called_once_with("crm_ext_cancel")

    def test_fallback_to_local_when_no_crm(
        self, client: TestClient, mock_db: MagicMock,
        sample_appointment: Appointment, tenant_id: UUID,
    ):
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = [sample_appointment]
        mock_db.execute.side_effect = [count_result, rows_result]
        with patch("app.admin.appointments._get_crm_adapter", return_value=None):
            resp = client.get("/admin/api/appointments")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["appointments"][0]["provider_name"] == "Dr. Smith"


class TestAdminAuthGuard:
    def _check_redirects(self, app, method: str, url: str, **kwargs):
        app.dependency_overrides.clear()
        with TestClient(app, follow_redirects=False) as c:
            resp = c.request(method, url, **kwargs)
        assert resp.status_code == 302
        assert resp.headers.get("location") == "/admin/login"

    def test_list_slots_requires_auth(self, app):
        self._check_redirects(app, "GET", "/admin/api/appointments/slots")

    def test_create_appointment_requires_auth(self, app):
        self._check_redirects(app, "POST", "/admin/api/appointments",
                              json={"patient_id": str(uuid4()), "provider_name": "Dr.",
                                    "start_time": "2026-01-01T09:00:00", "end_time": "2026-01-01T09:30:00"})

    def test_list_appointments_requires_auth(self, app):
        self._check_redirects(app, "GET", "/admin/api/appointments")

    def test_get_appointment_requires_auth(self, app):
        self._check_redirects(app, "GET", f"/admin/api/appointments/{uuid4()}")

    def test_update_appointment_requires_auth(self, app):
        self._check_redirects(app, "PATCH", f"/admin/api/appointments/{uuid4()}", json={"status": "confirmed"})

    def test_cancel_appointment_requires_auth(self, app):
        self._check_redirects(app, "POST", f"/admin/api/appointments/{uuid4()}/cancel")
