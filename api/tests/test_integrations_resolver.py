"""Unit tests for CRM adapter resolver."""
from __future__ import annotations

from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from app.integrations.base import AbstractCrmConnector
from app.integrations.resolver import CRM_PROVIDERS, get_crm_adapter, get_crm_adapter_for_tenant


def _mock_tenant(crm_provider: str = "pabau", has_config: bool = True) -> MagicMock:
    tenant = MagicMock()
    tenant.crm_config = {"api_key": "key"} if has_config else None
    tenant.crm_provider = crm_provider
    return tenant


# ── Registry ────────────────────────────────────────────────────────────────────────────


class TestCrmProvidersRegistry:
    def test_registry_has_pabau(self):
        assert "pabau" in CRM_PROVIDERS

    def test_registry_has_cliniko(self):
        assert "cliniko" in CRM_PROVIDERS

    def test_registry_values_are_classes(self):
        for cls in CRM_PROVIDERS.values():
            assert issubclass(cls, AbstractCrmConnector)

    def test_registry_is_dict(self):
        assert isinstance(CRM_PROVIDERS, dict)


# ── get_crm_adapter (by tenant_id) ──────────────────────────────────────────────────────


class TestGetCrmAdapter:
    def test_returns_pabau_connector(self):
        db = MagicMock(spec=Session)
        db.get.return_value = _mock_tenant("pabau")
        adapter = get_crm_adapter(tenant_id=MagicMock(), db=db)
        assert adapter is not None
        from app.integrations.pabau import PabauConnector
        assert isinstance(adapter, PabauConnector)

    def test_returns_cliniko_connector(self):
        db = MagicMock(spec=Session)
        db.get.return_value = _mock_tenant("cliniko")
        adapter = get_crm_adapter(tenant_id=MagicMock(), db=db)
        assert adapter is not None
        from app.integrations.cliniko import ClinikoConnector
        assert isinstance(adapter, ClinikoConnector)

    def test_returns_none_when_tenant_not_found(self):
        db = MagicMock(spec=Session)
        db.get.return_value = None
        adapter = get_crm_adapter(tenant_id=MagicMock(), db=db)
        assert adapter is None

    def test_returns_none_when_no_config(self):
        db = MagicMock(spec=Session)
        db.get.return_value = _mock_tenant("pabau", has_config=False)
        adapter = get_crm_adapter(tenant_id=MagicMock(), db=db)
        assert adapter is None

    def test_defaults_to_pabau_when_provider_unknown(self):
        db = MagicMock(spec=Session)
        tenant = _mock_tenant("pabau", has_config=True)
        tenant.crm_provider = None
        db.get.return_value = tenant
        adapter = get_crm_adapter(tenant_id=MagicMock(), db=db)
        assert adapter is not None
        from app.integrations.pabau import PabauConnector
        assert isinstance(adapter, PabauConnector)

    def test_returns_none_for_unknown_provider(self):
        db = MagicMock(spec=Session)
        db.get.return_value = _mock_tenant("nonexistent")
        adapter = get_crm_adapter(tenant_id=MagicMock(), db=db)
        assert adapter is None

    def test_passes_config_to_connector(self):
        db = MagicMock(spec=Session)
        tenant = _mock_tenant("pabau")
        tenant.crm_config = {"api_key": "custom-key", "company_id": 42}
        db.get.return_value = tenant
        adapter = get_crm_adapter(tenant_id=MagicMock(), db=db)
        assert adapter.api_key == "custom-key"

    def test_passes_cliniko_config(self):
        db = MagicMock(spec=Session)
        tenant = _mock_tenant("cliniko")
        tenant.crm_config = {"api_key": "ckey", "shard": "eu1", "user_agent": "TestApp"}
        db.get.return_value = tenant
        adapter = get_crm_adapter(tenant_id=MagicMock(), db=db)
        assert adapter.api_key == "ckey"
        assert adapter.shard == "eu1"


# ── get_crm_adapter_for_tenant (by Tenant object) ───────────────────────────────────────


class TestGetCrmAdapterForTenant:
    def test_returns_pabau_connector(self):
        tenant = _mock_tenant("pabau")
        adapter = get_crm_adapter_for_tenant(tenant)
        assert adapter is not None
        from app.integrations.pabau import PabauConnector
        assert isinstance(adapter, PabauConnector)

    def test_returns_cliniko_connector(self):
        tenant = _mock_tenant("cliniko")
        adapter = get_crm_adapter_for_tenant(tenant)
        assert adapter is not None
        from app.integrations.cliniko import ClinikoConnector
        assert isinstance(adapter, ClinikoConnector)

    def test_returns_none_when_no_config(self):
        tenant = _mock_tenant("pabau", has_config=False)
        adapter = get_crm_adapter_for_tenant(tenant)
        assert adapter is None

    def test_defaults_to_pabau(self):
        tenant = _mock_tenant("pabau")
        tenant.crm_provider = None
        adapter = get_crm_adapter_for_tenant(tenant)
        assert adapter is not None
        from app.integrations.pabau import PabauConnector
        assert isinstance(adapter, PabauConnector)

    def test_returns_none_for_unknown_provider(self):
        tenant = _mock_tenant("nonexistent")
        adapter = get_crm_adapter_for_tenant(tenant)
        assert adapter is None

    def test_passes_config(self):
        tenant = _mock_tenant("pabau")
        tenant.crm_config = {"api_key": "key1", "company_id": 99}
        adapter = get_crm_adapter_for_tenant(tenant)
        assert adapter.api_key == "key1"
