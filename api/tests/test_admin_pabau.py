from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app as _app
from app.models import Tenant


@pytest.fixture
def mock_tenant():
    t = MagicMock(spec=Tenant)
    t.id = uuid4()
    t.crm_config = {}
    t.crm_provider = "pabau"
    return t


@pytest.fixture
def client(mock_tenant):
    def _override():
        return mock_tenant

    _app.dependency_overrides.clear()
    from app.admin.deps import get_admin_tenant
    _app.dependency_overrides[get_admin_tenant] = _override
    with TestClient(_app) as c:
        yield c
    _app.dependency_overrides.clear()


class TestConfigureCrm:
    def test_saves_shard(self, client, mock_tenant):
        resp = client.post("/admin/api/crm/configure", json={
            "api_key": "key123",
            "company_id": "cid456",
            "webhook_secret": "whsec",
            "shard": "eu1",
            "crm_provider": "pabau",
        })
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert mock_tenant.crm_config["shard"] == "eu1"

    def test_saves_api_key(self, client, mock_tenant):
        resp = client.post("/admin/api/crm/configure", json={
            "api_key": "newkey",
            "company_id": "cid",
            "webhook_secret": "",
            "shard": "",
            "crm_provider": "pabau",
        })
        assert resp.status_code == 200
        assert mock_tenant.crm_config["api_key"] == "newkey"

    def test_saves_crm_provider(self, client, mock_tenant):
        resp = client.post("/admin/api/crm/configure", json={
            "api_key": "k",
            "company_id": "",
            "webhook_secret": "",
            "shard": "",
            "crm_provider": "cliniko",
        })
        assert resp.status_code == 200
        assert mock_tenant.crm_provider == "cliniko"

    def test_disconnect_clears_config(self, client, mock_tenant):
        mock_tenant.crm_config = {"api_key": "old"}
        resp = client.post("/admin/api/crm/disconnect")
        assert resp.status_code == 200
        assert mock_tenant.crm_config == {}
