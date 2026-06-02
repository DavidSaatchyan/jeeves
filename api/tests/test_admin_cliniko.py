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
    def _patch_discover(self, shard: str | None = "au1"):
        return patch("app.admin.cliniko._discover_shard", return_value=shard)

    def test_saves_api_key_and_detected_shard(self, client, mock_tenant):
        with self._patch_discover("eu1"):
            resp = client.post("/admin/api/cliniko/configure", json={
                "api_key": "cliniko-key-123",
            })
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert mock_tenant.crm_config["api_key"] == "cliniko-key-123"
        assert mock_tenant.crm_config["shard"] == "eu1"

    def test_sets_crm_provider(self, client, mock_tenant):
        with self._patch_discover():
            resp = client.post("/admin/api/cliniko/configure", json={
                "api_key": "k",
            })
        assert resp.status_code == 200
        assert mock_tenant.crm_provider == "cliniko"

    def test_sets_user_agent(self, client, mock_tenant):
        with self._patch_discover():
            client.post("/admin/api/cliniko/configure", json={
                "api_key": "k",
            })
        assert "Jeeves" in mock_tenant.crm_config["user_agent"]

    def test_returns_connected_true_when_discovered(self, client, mock_tenant):
        with self._patch_discover("au1"):
            resp = client.post("/admin/api/cliniko/configure", json={
                "api_key": "k",
            })
        assert resp.json()["connected"] is True
        assert "Connected" in resp.json()["message"]

    def test_returns_connected_false_when_no_shard_discovered(self, client, mock_tenant):
        with self._patch_discover(None):
            resp = client.post("/admin/api/cliniko/configure", json={
                "api_key": "k",
            })
        assert resp.status_code == 200
        assert resp.json()["connected"] is False
        assert "failed" in resp.json()["message"].lower()

    def test_does_not_save_when_discovery_fails(self, client, mock_tenant):
        with self._patch_discover(None):
            client.post("/admin/api/cliniko/configure", json={
                "api_key": "k",
            })
        assert mock_tenant.crm_config == {}
        assert mock_tenant.crm_provider == ""

    def test_rejects_empty_api_key(self, client, mock_tenant):
        resp = client.post("/admin/api/cliniko/configure", json={
            "api_key": "",
        })
        assert resp.status_code == 400
        assert "required" in resp.json()["detail"].lower()
        assert mock_tenant.crm_config == {}

    def test_rejects_missing_api_key(self, client, mock_tenant):
        resp = client.post("/admin/api/cliniko/configure", json={})
        assert resp.status_code == 422  # Pydantic validation


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


class TestShardFromKey:
    def test_extracts_shard_from_key_suffix(self):
        from app.admin.cliniko import _shard_from_key
        assert _shard_from_key("base64stuff-au5") == "au5"

    def test_returns_none_when_no_dash(self):
        from app.admin.cliniko import _shard_from_key
        assert _shard_from_key("justakey") is None

    def test_returns_none_when_unknown_shard(self):
        from app.admin.cliniko import _shard_from_key
        assert _shard_from_key("base64stuff-zz9") is None

    def test_returns_none_when_too_short(self):
        from app.admin.cliniko import _shard_from_key
        assert _shard_from_key("ab") is None


class TestDiscoverShard:
    def test_uses_shard_from_key_when_valid(self):
        from app.admin.cliniko import _discover_shard
        with patch("app.admin.cliniko._try_shard", return_value=True) as mock_try:
            result = _discover_shard("base64stuff-au4")
        assert result == "au4"
        mock_try.assert_called_once_with("base64stuff-au4", "au4")

    def test_falls_back_to_probe_when_no_suffix(self):
        from app.admin.cliniko import _discover_shard
        with patch("app.admin.cliniko._try_shard") as mock_try:
            mock_try.side_effect = lambda k, s: s == "ca1"
            result = _discover_shard("justkey")
        assert result == "ca1"

    def test_falls_back_to_probe_when_suffix_shard_fails(self):
        from app.admin.cliniko import _discover_shard
        with patch("app.admin.cliniko._try_shard") as mock_try:
            mock_try.side_effect = lambda k, s: s == "ca1"
            result = _discover_shard("base64stuff-au1")
        assert result == "ca1"

    def test_returns_none_when_all_fail(self):
        from app.admin.cliniko import _discover_shard
        with patch("app.admin.cliniko._try_shard", return_value=False):
            result = _discover_shard("key")
        assert result is None

    def test_try_shard_correct_url_and_auth(self):
        from app.admin.cliniko import _try_shard
        with patch("app.admin.cliniko.httpx.get") as mock_get:
            mock_get.return_value.status_code = 200
            result = _try_shard("test-key", "eu1")
        assert result is True
        url = mock_get.call_args[0][0]
        assert "eu1" in url
        assert "/practitioners" in url
        headers = mock_get.call_args[1]["headers"]
        assert "Basic" in headers["Authorization"]
        assert "Jeeves" in headers["User-Agent"]
