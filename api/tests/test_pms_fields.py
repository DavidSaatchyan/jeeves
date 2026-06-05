"""Tests for shared/pms_fields.py — upsert_objects + field maps."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import PmsService
from app.shared.pms_fields import clinic_fields, practitioner_fields, service_fields, upsert_objects


class TestUpsertObjects:
    def test_create_new(self):
        db = MagicMock(spec=Session)
        db.execute.return_value.scalars.return_value.all.return_value = []
        tenant_id = uuid4()
        items = [{"id": "ext-1", "name": "Alpha"}, {"id": "ext-2", "name": "Beta"}]
        with patch("app.shared.pms_fields.select"):
            count = upsert_objects(db, PmsService, tenant_id, items, "id", lambda x: {"name": x["name"]})
        assert count == 2
        assert db.add.call_count == 2
        db.flush.assert_called_once()

    def test_update_existing(self):
        existing = MagicMock()
        existing.external_id = "ext-1"
        db = MagicMock(spec=Session)
        db.execute.return_value.scalars.return_value.all.return_value = [existing]
        tenant_id = uuid4()
        items = [{"id": "ext-1", "name": "Updated"}]
        with patch("app.shared.pms_fields.select"):
            count = upsert_objects(db, PmsService, tenant_id, items, "id", lambda x: {"name": x["name"]})
        assert count == 1
        assert existing.name == "Updated"
        assert db.add.call_count == 0

    def test_empty_items(self):
        db = MagicMock(spec=Session)
        count = upsert_objects(db, PmsService, uuid4(), [], "id", lambda x: {})
        assert count == 0
        db.execute.assert_not_called()

    def test_missing_id_skipped(self):
        db = MagicMock(spec=Session)
        items = [{"name": "NoId"}]
        with patch("app.shared.pms_fields.select"):
            count = upsert_objects(db, PmsService, uuid4(), items, "id", lambda x: {"name": x["name"]})
        assert count == 0
        assert db.add.call_count == 0

    def test_mixed_create_and_update(self):
        existing = MagicMock()
        existing.external_id = "ext-1"
        existing.name = "Keep"
        db = MagicMock(spec=Session)
        db.execute.return_value.scalars.return_value.all.return_value = [existing]
        items = [{"id": "ext-1", "name": "Changed"}, {"id": "ext-2", "name": "New"}]
        with patch("app.shared.pms_fields.select"):
            count = upsert_objects(db, PmsService, uuid4(), items, "id", lambda x: {"name": x["name"]})
        assert count == 2
        assert existing.name == "Changed"
        assert db.add.call_count == 1


class TestServiceFields:
    def test_minimal(self):
        result = service_fields({})
        assert result["name"] == ""
        assert result["price_cents"] == 0
        assert result["online_bookable"] is True

    def test_full(self):
        item = {
            "name": "Consultation",
            "description": "Initial visit",
            "price": 15000,
            "duration_in_minutes": 60,
            "category": "Consultation",
            "telehealth_enabled": True,
            "online_booking_enabled": False,
        }
        result = service_fields(item)
        assert result["name"] == "Consultation"
        assert result["price_cents"] == 15000
        assert result["duration_minutes"] == 60
        assert result["telehealth_enabled"] is True
        assert result["online_bookable"] is False

    def test_price_as_float(self):
        result = service_fields({"price": 99.99})
        assert result["price_cents"] == 9999

    def test_online_bookable_fallback(self):
        result = service_fields({"online_bookable": False})
        assert result["online_bookable"] is False


class TestPractitionerFields:
    def test_minimal(self):
        result = practitioner_fields({})
        assert result["display_name"] == ""
        assert result["active"] is True

    def test_full(self):
        item = {
            "display_name": "Dr. Smith",
            "title": "DDS",
            "designation": "Senior",
            "description": "Experienced dentist",
            "active": False,
        }
        result = practitioner_fields(item)
        assert result["display_name"] == "Dr. Smith"
        assert result["title"] == "DDS"
        assert result["active"] is False

    def test_display_name_fallback_first_name(self):
        result = practitioner_fields({"first_name": "Jane"})
        assert result["display_name"] == "Jane"

    def test_active_default_true(self):
        result = practitioner_fields({"active": False})
        assert result["active"] is False


class TestClinicFields:
    def test_minimal(self):
        result = clinic_fields({})
        assert result["business_name"] == ""
        assert result["phone"] == ""

    def test_full(self):
        item = {
            "business_name": "My Clinic",
            "address": "123 Main St",
            "city": "Springfield",
            "state": "IL",
            "postcode": "62701",
            "country": "US",
            "phone": "+1-555-0100",
            "email": "info@clinic.com",
            "website": "https://clinic.com",
            "timezone": "America/Chicago",
        }
        result = clinic_fields(item)
        assert result["business_name"] == "My Clinic"
        assert result["address"] == "123 Main St"
        assert result["timezone"] == "America/Chicago"

    def test_name_fallback(self):
        result = clinic_fields({"name": "Fallback Clinic"})
        assert result["business_name"] == "Fallback Clinic"


class TestFieldMapsImport:
    """Verify knowledge/sync.py and core/crm_sync.py import from shared.pms_fields."""

    def test_knowledge_sync_imports(self):
        from app.knowledge import sync as ks
        assert ks.upsert_objects is upsert_objects
        assert ks.service_fields is service_fields
        assert ks.practitioner_fields is practitioner_fields
        assert ks.clinic_fields is clinic_fields

    def test_core_crm_sync_imports(self):
        from app.core import crm_sync as cs
        assert cs.upsert_objects is upsert_objects
        assert cs.service_fields is service_fields
        assert cs.practitioner_fields is practitioner_fields
        assert cs.clinic_fields is clinic_fields
