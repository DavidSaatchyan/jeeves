from __future__ import annotations

from typing import Any, get_type_hints

import pytest

from app.integrations.crm.base import AbstractCrmConnector


class TestAbstractCrmConnector:
    def test_cannot_instantiate_abstract_class(self):
        with pytest.raises(TypeError):
            AbstractCrmConnector()  # type: ignore[abstract]

    def test_phi_safe_default_is_false(self):
        assert AbstractCrmConnector.phi_safe is False

    def test_abstract_methods_present(self):
        methods = [
            "get_patient",
            "find_patient",
            "create_patient",
            "update_patient",
            "create_appointment",
            "update_appointment",
            "cancel_appointment",
            "get_patient_appointments",
            "search_available_slots",
            "verify_webhook_signature",
            "parse_webhook_event",
        ]
        for name in methods:
            assert hasattr(AbstractCrmConnector, name)
            assert callable(getattr(AbstractCrmConnector, name))

    def test_get_patient_signature(self):
        hints = get_type_hints(AbstractCrmConnector.get_patient)
        assert hints["patient_id"] is str
        assert hints["return"] == dict[str, Any] | None

    def test_find_patient_signature(self):
        hints = get_type_hints(AbstractCrmConnector.find_patient)
        assert hints["email"] == str | None
        assert hints["phone"] == str | None
        assert hints["return"] == dict[str, Any] | None

    def test_create_patient_signature(self):
        hints = get_type_hints(AbstractCrmConnector.create_patient)
        assert hints["data"] == dict[str, Any]
        assert hints["return"] == dict[str, Any]

    def test_update_patient_signature(self):
        hints = get_type_hints(AbstractCrmConnector.update_patient)
        assert hints["patient_id"] is str
        assert hints["data"] == dict[str, Any]
        assert hints["return"] == dict[str, Any]

    def test_create_appointment_signature(self):
        hints = get_type_hints(AbstractCrmConnector.create_appointment)
        assert hints["patient_id"] is str
        assert hints["data"] == dict[str, Any]
        assert hints["return"] == dict[str, Any]

    def test_update_appointment_signature(self):
        hints = get_type_hints(AbstractCrmConnector.update_appointment)
        assert hints["appt_id"] is str
        assert hints["data"] == dict[str, Any]
        assert hints["return"] == dict[str, Any]

    def test_cancel_appointment_signature(self):
        hints = get_type_hints(AbstractCrmConnector.cancel_appointment)
        assert hints["appt_id"] is str
        assert hints["return"] is bool

    def test_get_patient_appointments_signature(self):
        hints = get_type_hints(AbstractCrmConnector.get_patient_appointments)
        assert hints["patient_id"] is str
        assert hints["return"] == list[dict[str, Any]]

    def test_search_available_slots_signature(self):
        hints = get_type_hints(AbstractCrmConnector.search_available_slots)
        assert hints["doctor_id"] is str
        assert hints["date"] is str
        assert hints["return"] == list[dict[str, Any]]

    def test_verify_webhook_signature_signature(self):
        hints = get_type_hints(AbstractCrmConnector.verify_webhook_signature)
        assert hints["payload"] is bytes
        assert hints["signature"] is str
        assert hints["return"] is bool

    def test_parse_webhook_event_signature(self):
        hints = get_type_hints(AbstractCrmConnector.parse_webhook_event)
        assert hints["payload"] == dict[str, Any]
        assert hints["return"] == dict[str, Any]
