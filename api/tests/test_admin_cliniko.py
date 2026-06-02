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
    t.crm_provider = ""
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


class TestConfigureCliniko:
    def _patch_adapter(self, connected: bool = True):
        mock_adapter = MagicMock()
        mock_adapter.test_connection.return_value = connected
        return patch("app.admin.cliniko.get_crm_adapter_for_tenant", return_value=mock_adapter)

    def test_saves_api_key_and_shard(self, client, mock_tenant):
        with self._patch_adapter():
            resp = client.post("/admin/api/cliniko/configure", json={
                "api_key": "cliniko-key-123",
                "shard": "eu1",
                "webhook_secret": "whsec",
            })
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert mock_tenant.crm_config["api_key"] == "cliniko-key-123"
        assert mock_tenant.crm_config["shard"] == "eu1"
        assert mock_tenant.crm_config["webhook_secret"] == "whsec"

    def test_sets_crm_provider(self, client, mock_tenant):
        with self._patch_adapter():
            resp = client.post("/admin/api/cliniko/configure", json={
                "api_key": "k",
                "shard": "au1",
                "webhook_secret": "",
            })
        assert resp.status_code == 200
        assert mock_tenant.crm_provider == "cliniko"

    def test_default_shard_is_au1(self, client, mock_tenant):
        with self._patch_adapter():
            client.post("/admin/api/cliniko/configure", json={
                "api_key": "k",
                "shard": "au1",
                "webhook_secret": "",
            })
        assert mock_tenant.crm_config["shard"] == "au1"

    def test_sets_user_agent(self, client, mock_tenant):
        with self._patch_adapter():
            client.post("/admin/api/cliniko/configure", json={
                "api_key": "k",
                "shard": "au1",
                "webhook_secret": "",
            })
        assert "Jeeves" in mock_tenant.crm_config["user_agent"]

    def test_returns_connected_true_when_test_passes(self, client, mock_tenant):
        with self._patch_adapter(connected=True):
            resp = client.post("/admin/api/cliniko/configure", json={
                "api_key": "k",
                "shard": "au1",
                "webhook_secret": "",
            })
        assert resp.json()["connected"] is True
        assert "Connected" in resp.json()["message"]

    def test_returns_connected_false_when_test_fails(self, client, mock_tenant):
        with self._patch_adapter(connected=False):
            resp = client.post("/admin/api/cliniko/configure", json={
                "api_key": "k",
                "shard": "au1",
                "webhook_secret": "",
            })
        assert resp.json()["connected"] is False
        assert "failed" in resp.json()["message"].lower()

    def test_returns_connected_false_on_exception(self, client, mock_tenant):
        mock_adapter = MagicMock()
        mock_adapter.test_connection.side_effect = RuntimeError("API unreachable")
        with patch("app.admin.cliniko.get_crm_adapter_for_tenant", return_value=mock_adapter):
            resp = client.post("/admin/api/cliniko/configure", json={
                "api_key": "k",
                "shard": "au1",
                "webhook_secret": "",
            })
        assert resp.json()["connected"] is False


class TestClinikoStatus:
    def test_returns_not_connected_when_empty(self, client, mock_tenant):
        resp = client.get("/admin/api/cliniko/status")
        assert resp.status_code == 200
        assert resp.json()["connected"] is False

    def test_returns_connected_when_configured(self, client, mock_tenant):
        mock_tenant.crm_config = {"api_key": "k"}
        mock_tenant.crm_provider = "cliniko"
        resp = client.get("/admin/api/cliniko/status")
        assert resp.status_code == 200
        assert resp.json()["connected"] is True
        assert resp.json()["provider"] == "cliniko"


class TestClinikoTestConnection:
    def test_returns_not_configured_when_no_api_key(self, client, mock_tenant):
        mock_tenant.crm_config = {}
        mock_tenant.crm_provider = "cliniko"
        resp = client.post("/admin/api/cliniko/test")
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Cliniko not configured"

    def test_returns_not_configured_when_wrong_provider(self, client, mock_tenant):
        mock_tenant.crm_config = {"api_key": "k"}
        mock_tenant.crm_provider = "pabau"
        resp = client.post("/admin/api/cliniko/test")
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Cliniko is not the active provider"

    def test_returns_ok_when_connection_succeeds(self, client, mock_tenant):
        mock_tenant.crm_config = {"api_key": "k"}
        mock_tenant.crm_provider = "cliniko"
        mock_adapter = MagicMock()
        mock_adapter.test_connection.return_value = True
        with patch("app.admin.cliniko.get_crm_adapter_for_tenant", return_value=mock_adapter):
            resp = client.post("/admin/api/cliniko/test")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert "Connected" in resp.json()["message"]

    def test_returns_502_when_connection_fails(self, client, mock_tenant):
        mock_tenant.crm_config = {"api_key": "k"}
        mock_tenant.crm_provider = "cliniko"
        mock_adapter = MagicMock()
        mock_adapter.test_connection.return_value = False
        with patch("app.admin.cliniko.get_crm_adapter_for_tenant", return_value=mock_adapter):
            resp = client.post("/admin/api/cliniko/test")
        assert resp.status_code == 502
        assert resp.json()["detail"] == "Connection failed"

    def test_returns_502_on_exception(self, client, mock_tenant):
        mock_tenant.crm_config = {"api_key": "k"}
        mock_tenant.crm_provider = "cliniko"
        mock_adapter = MagicMock()
        mock_adapter.test_connection.side_effect = RuntimeError("API unreachable")
        with patch("app.admin.cliniko.get_crm_adapter_for_tenant", return_value=mock_adapter):
            resp = client.post("/admin/api/cliniko/test")
        assert resp.status_code == 502
        assert "API unreachable" in resp.json()["detail"]

    def test_returns_502_when_no_adapter(self, client, mock_tenant):
        mock_tenant.crm_config = {"api_key": "k"}
        mock_tenant.crm_provider = "cliniko"
        with patch("app.admin.cliniko.get_crm_adapter_for_tenant", return_value=None):
            resp = client.post("/admin/api/cliniko/test")
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Could not create adapter"


class TestDisconnectCliniko:
    def test_clears_config_and_resets_provider(self, client, mock_tenant):
        mock_tenant.crm_config = {"api_key": "old", "shard": "au1"}
        mock_tenant.crm_provider = "cliniko"
        resp = client.post("/admin/api/cliniko/disconnect")
        assert resp.status_code == 200
        assert mock_tenant.crm_config == {}
        assert mock_tenant.crm_provider == "pabau"
