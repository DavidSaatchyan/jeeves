"""Tests for shared/hms_schemas.py — field schema registry + validation."""
from __future__ import annotations

from app.shared.hms_schemas import HMS_FIELD_SCHEMAS, validate_hms_records


class TestHmsFieldSchemas:
    def test_cliniko_service_schema(self):
        schema = HMS_FIELD_SCHEMAS["cliniko"]["service"]
        assert "id" in schema
        assert "name" in schema
        assert "item_type" in schema
        assert "price" in schema

    def test_cliniko_practitioner_schema(self):
        schema = HMS_FIELD_SCHEMAS["cliniko"]["practitioner"]
        assert "id" in schema
        assert "first_name" in schema
        assert "last_name" in schema

    def test_cliniko_clinic_schema(self):
        schema = HMS_FIELD_SCHEMAS["cliniko"]["clinic"]
        assert "id" in schema
        assert "name" in schema
        assert "business_name" in schema

    def test_pabau_service_schema(self):
        schema = HMS_FIELD_SCHEMAS["pabau"]["service"]
        assert "id" in schema
        assert "name" in schema

    def test_pabau_practitioner_schema(self):
        schema = HMS_FIELD_SCHEMAS["pabau"]["practitioner"]
        assert "id" in schema
        assert "display_name" in schema

    def test_pabau_clinic_schema_empty(self):
        assert HMS_FIELD_SCHEMAS["pabau"]["clinic"] == set()


class TestValidateHmsRecords:
    def test_valid_records_no_warnings(self):
        records = [{"id": "1", "name": "Consult", "item_type": "Service", "price": 15000}]
        warnings = validate_hms_records("cliniko", "service", records)
        assert warnings == []

    def test_missing_field_logs_warning(self):
        records = [{"id": "1", "name": "Consult"}]  # missing item_type, price
        warnings = validate_hms_records("cliniko", "service", records)
        assert len(warnings) == 1
        assert "missing fields" in warnings[0]

    def test_multiple_records_with_missing_fields(self):
        records = [
            {"id": "1", "name": "A", "item_type": "Service", "price": 100},
            {"id": "2"},  # missing name, item_type, price
        ]
        warnings = validate_hms_records("cliniko", "service", records)
        assert len(warnings) == 1

    def test_unknown_provider_returns_no_warnings(self):
        records = [{"id": "1"}]
        warnings = validate_hms_records("unknown_provider", "service", records)
        assert warnings == []

    def test_unknown_entity_type_returns_no_warnings(self):
        records = [{"id": "1"}]
        warnings = validate_hms_records("cliniko", "unknown_entity", records)
        assert warnings == []

    def test_empty_records_no_warnings(self):
        warnings = validate_hms_records("cliniko", "service", [])
        assert warnings == []

    def test_pabau_service_missing_name(self):
        records = [{"id": "1"}]  # missing name
        warnings = validate_hms_records("pabau", "service", records)
        assert len(warnings) == 1
        assert "missing fields" in warnings[0]

    def test_pabau_clinic_no_warnings(self):
        records = [{"id": "1", "business_name": "Test"}]
        warnings = validate_hms_records("pabau", "clinic", records)
        assert warnings == []
