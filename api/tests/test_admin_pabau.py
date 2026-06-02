from __future__ import annotations

from unittest.mock import MagicMock, patch
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


class TestCrmStatus:
    def test_returns_not_connected_when_empty(self, client, mock_tenant):
        mock_tenant.crm_config = {}
        resp = client.get("/admin/api/crm/status")
        assert resp.status_code == 200
        assert resp.json()["connected"] is False

    def test_returns_connected_when_configured(self, client, mock_tenant):
        mock_tenant.crm_config = {"api_key": "k"}
        resp = client.get("/admin/api/crm/status")
        assert resp.status_code == 200
        assert resp.json()["connected"] is True

    def test_returns_provider(self, client, mock_tenant):
        mock_tenant.crm_provider = "pabau"
        resp = client.get("/admin/api/crm/status")
        assert resp.json()["provider"] == "pabau"


class TestCrmTestConnection:
    def test_returns_not_configured_when_no_api_key(self, client, mock_tenant):
        mock_tenant.crm_config = {}
        resp = client.post("/admin/api/crm/test")
        assert resp.status_code == 400
        assert "not configured" in resp.json()["detail"]

    def test_returns_ok_when_connection_succeeds(self, client, mock_tenant):
        mock_tenant.crm_config = {"api_key": "k"}
        mock_adapter = MagicMock()
        mock_adapter.test_connection.return_value = True
        with patch("app.admin.pabau.get_crm_adapter_for_tenant", return_value=mock_adapter):
            resp = client.post("/admin/api/crm/test")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_returns_502_when_connection_fails(self, client, mock_tenant):
        mock_tenant.crm_config = {"api_key": "k"}
        mock_adapter = MagicMock()
        mock_adapter.test_connection.return_value = False
        with patch("app.admin.pabau.get_crm_adapter_for_tenant", return_value=mock_adapter):
            resp = client.post("/admin/api/crm/test")
        assert resp.status_code == 502

    def test_returns_502_on_exception(self, client, mock_tenant):
        mock_tenant.crm_config = {"api_key": "k"}
        mock_adapter = MagicMock()
        mock_adapter.test_connection.side_effect = RuntimeError("fail")
        with patch("app.admin.pabau.get_crm_adapter_for_tenant", return_value=mock_adapter):
            resp = client.post("/admin/api/crm/test")
        assert resp.status_code == 502

    def test_returns_400_when_no_adapter(self, client, mock_tenant):
        mock_tenant.crm_config = {"api_key": "k"}
        with patch("app.admin.pabau.get_crm_adapter_for_tenant", return_value=None):
            resp = client.post("/admin/api/crm/test")
        assert resp.status_code == 400


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
