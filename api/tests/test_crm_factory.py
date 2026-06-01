from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from app.crypto import ConnectorError
from app.integrations.crm import (
    _registry,
    get_crm_adapter,
    list_crm_providers,
    register_crm_provider,
)
from app.integrations.crm.base import AbstractCrmConnector


class _MockAdapter(AbstractCrmConnector):
    provider = "mock_test"
    phi_safe = True

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def get_patient(self, patient_id: str) -> dict[str, Any] | None:
        return {"id": patient_id}

    def find_patient(self, email: str | None = None, phone: str | None = None) -> dict[str, Any] | None:
        return None

    def create_patient(self, data: dict[str, Any]) -> dict[str, Any]:
        return {"id": "new"}

    def update_patient(self, patient_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"id": patient_id}

    def create_appointment(self, patient_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"id": "appt"}

    def update_appointment(self, appt_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return {"id": appt_id}

    def cancel_appointment(self, appt_id: str) -> bool:
        return True

    def get_patient_appointments(self, patient_id: str) -> list[dict[str, Any]]:
        return []

    def get_appointment(self, appt_id: str) -> dict[str, Any] | None:
        return {"id": appt_id, "status": "scheduled"}

    def list_appointments(
        self,
        tenant_id: str,
        status: str | None = None,
        provider: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        patient_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict:
        return {"total": 0, "items": []}

    def search_available_slots(self, doctor_id: str, date: str) -> list[dict[str, Any]]:
        return []

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        return True

    def parse_webhook_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"event": "test", "resource": {}}


@pytest.fixture(autouse=True)
def _isolate_registry():
    original = dict(_registry)
    _registry.clear()
    yield
    _registry.update(original)


class TestRegisterCrmProvider:
    def test_registers_new_provider(self):
        register_crm_provider("mock_test", _MockAdapter)
        assert "mock_test" in _registry
        assert _registry["mock_test"] is _MockAdapter

    def test_overwrites_existing(self):
        register_crm_provider("dup", _MockAdapter)
        other = MagicMock(spec=AbstractCrmConnector)
        register_crm_provider("dup", other)
        assert _registry["dup"] is other

    def test_registry_accepts_multiple_providers(self):
        register_crm_provider("a", _MockAdapter)
        register_crm_provider("b", _MockAdapter)
        assert len(_registry) == 2


class TestGetCrmAdapter:
    def test_returns_adapter_instance(self):
        register_crm_provider("mock_test", _MockAdapter)
        adapter = get_crm_adapter("mock_test", {"key": "val"})
        assert isinstance(adapter, _MockAdapter)
        assert adapter.config == {"key": "val"}

    def test_raises_connector_error_for_unknown_provider(self):
        with pytest.raises(ConnectorError) as excinfo:
            get_crm_adapter("nonexistent", {})
        assert "nonexistent" in str(excinfo.value)

    def test_raises_connector_error_when_empty_provider(self):
        with pytest.raises(ConnectorError):
            get_crm_adapter("", {})

    def test_passes_config_to_adapter(self):
        register_crm_provider("mock_test", _MockAdapter)
        config = {"base_url": "https://example.com", "token": "abc"}
        adapter = get_crm_adapter("mock_test", config)
        assert adapter.config["base_url"] == "https://example.com"
        assert adapter.config["token"] == "abc"


class TestListCrmProviders:
    def test_returns_empty_when_no_providers(self):
        assert list_crm_providers() == []

    def test_returns_registered_names(self):
        register_crm_provider("alpha", _MockAdapter)
        register_crm_provider("beta", _MockAdapter)
        providers = list_crm_providers()
        assert "alpha" in providers
        assert "beta" in providers
        assert len(providers) == 2

    def test_does_not_contain_unregistered(self):
        register_crm_provider("only_me", _MockAdapter)
        assert "nonexistent" not in list_crm_providers()
