"""Unit tests for WhatsApp messaging helpers and channel config CRUD."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.orm import Session

from app.channels.whatsapp import _api_url, _send_message, _maybe_crm_bridge, validate_config
from app.channels.registry import upsert_channel, get_channel, delete_channel, list_all_configs
from app.models import ChannelConfig


# ── _api_url ────────────────────────────────────────────────────────────────────────────

class TestApiUrl:
    def test_formats_with_phone_number_id(self):
        url = _api_url("123456789")
        assert url == "https://graph.facebook.com/v17.0/123456789/messages"

    def test_handles_string_phone_id(self):
        url = _api_url("ABC123")
        assert "ABC123" in url


# ── _send_message ───────────────────────────────────────────────────────────────────────

class TestSendMessage:
    def test_success(self):
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.json.return_value = {"messages": [{"id": "wamid.abc123"}]}

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = asyncio.run(_send_message("123", "token", "+15551112222", "Hello"))

        assert result == {"messages": [{"id": "wamid.abc123"}]}
        mock_client.post.assert_called_once_with(
            "https://graph.facebook.com/v17.0/123/messages",
            headers={
                "Authorization": "Bearer token",
                "Content-Type": "application/json",
            },
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": "+15551112222",
                "type": "text",
                "text": {"body": "Hello"},
            },
        )

    def test_http_error_propagates(self):
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "401 Unauthorized", request=MagicMock(), response=mock_response,
        )

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(httpx.HTTPStatusError):
                asyncio.run(_send_message("123", "bad_token", "+15551112222", "Hello"))

    def test_timeout_config(self):
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.json.return_value = {}

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client

        with patch("httpx.AsyncClient", return_value=mock_client) as patched:
            asyncio.run(_send_message("123", "token", "+1", "Hi"))
            patched.assert_called_once_with(timeout=15.0)


# ── _maybe_crm_bridge ───────────────────────────────────────────────────────────────────

class TestMaybeCrmBridge:
    def _make_tenant(self, config=None, use_default=True):
        tenant = MagicMock()
        tenant.crm_config = config if not use_default else {"api_key": "test", "company_id": "123"}
        tenant.crm_provider = "pabau"
        return tenant

    def test_creates_new_patient(self, mock_db):
        mock_db.get.return_value = self._make_tenant()
        mock_adapter = MagicMock()
        mock_adapter.find_patient.return_value = None

        with patch("app.channels.whatsapp.get_crm_adapter", return_value=mock_adapter):
            _maybe_crm_bridge(mock_db, uuid4(), "+15551112222", "Hello", "John Doe")

        mock_adapter.find_patient.assert_called_once_with(phone="+15551112222")
        mock_adapter.create_patient.assert_called_once_with({
            "first_name": "John",
            "last_name": "Doe",
            "phone": "+15551112222",
        })

    def test_skips_if_patient_exists(self, mock_db):
        mock_db.get.return_value = self._make_tenant()
        mock_adapter = MagicMock()
        mock_adapter.find_patient.return_value = {"id": "existing_patient"}

        with patch("app.channels.whatsapp.get_crm_adapter", return_value=mock_adapter):
            _maybe_crm_bridge(mock_db, uuid4(), "+15551112222", "Hello", "John")

        mock_adapter.create_patient.assert_not_called()

    def test_handles_no_contact_name(self, mock_db):
        mock_db.get.return_value = self._make_tenant()
        mock_adapter = MagicMock()
        mock_adapter.find_patient.return_value = None

        with patch("app.channels.whatsapp.get_crm_adapter", return_value=mock_adapter):
            _maybe_crm_bridge(mock_db, uuid4(), "+15551112222", "Hello", None)

        mock_adapter.create_patient.assert_called_once_with({
            "first_name": "WhatsApp",
            "last_name": "User",
            "phone": "+15551112222",
        })

    def test_skips_if_no_pabau_config(self, mock_db):
        mock_db.get.return_value = self._make_tenant(use_default=False)
        with patch("app.channels.whatsapp.get_crm_adapter", return_value=None) as mock_fn:
            _maybe_crm_bridge(mock_db, uuid4(), "+15551112222", "Hello", "John")
        mock_fn.assert_called_once()

    def test_skips_if_empty_crm_config(self, mock_db):
        mock_db.get.return_value = self._make_tenant(config={}, use_default=False)
        with patch("app.channels.whatsapp.get_crm_adapter", return_value=None):
            _maybe_crm_bridge(mock_db, uuid4(), "+15551112222", "Hello", "John")

    def test_silently_handles_adapter_error(self, mock_db):
        mock_db.get.return_value = self._make_tenant()
        mock_adapter = MagicMock()
        mock_adapter.find_patient.side_effect = Exception("CRM timeout")

        with patch("app.channels.whatsapp.get_crm_adapter", return_value=mock_adapter):
            _maybe_crm_bridge(mock_db, uuid4(), "+15551112222", "Hello", "John")

    def test_single_name_uses_user_fallback(self, mock_db):
        mock_db.get.return_value = self._make_tenant()
        mock_adapter = MagicMock()
        mock_adapter.find_patient.return_value = None

        with patch("app.channels.whatsapp.get_crm_adapter", return_value=mock_adapter):
            _maybe_crm_bridge(mock_db, uuid4(), "+15551112222", "Hello", "Alice")

        mock_adapter.create_patient.assert_called_once_with({
            "first_name": "Alice",
            "last_name": "User",
            "phone": "+15551112222",
        })


# ── validate_config ─────────────────────────────────────────────────────────────────────

class TestValidateConfig:
    def test_valid_config(self):
        config = {
            "phone_number_id": "123456789",
            "access_token": "my_access_token",
            "verify_token": "abc",
        }
        valid, msg = validate_config(config)
        assert valid is True
        assert msg == "Config looks valid"

    def test_missing_phone_number_id(self):
        config = {"access_token": "my_access_token"}
        valid, msg = validate_config(config)
        assert valid is False
        assert "phone_number_id" in msg

    def test_missing_access_token(self):
        config = {"phone_number_id": "123456789"}
        valid, msg = validate_config(config)
        assert valid is False
        assert "access_token" in msg

    def test_empty_values(self):
        config = {"phone_number_id": "", "access_token": ""}
        valid, msg = validate_config(config)
        assert valid is False

    def test_empty_dict(self):
        valid, msg = validate_config({})
        assert valid is False


# ── Channel Config CRUD ─────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)


class TestChannelConfigCrud:
    def test_upsert_new_channel(self, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        tenant_id = uuid4()

        result = upsert_channel(mock_db, tenant_id, "whatsapp", {"key": "val"}, "active")

        assert result.channel_type == "whatsapp"
        assert result.config == {"key": "val"}
        assert result.status == "active"
        assert result.tenant_id == tenant_id
        mock_db.add.assert_called_once()

    def test_upsert_existing_channel(self, mock_db):
        existing = MagicMock(spec=ChannelConfig)
        existing.channel_type = "whatsapp"
        existing.config = {"old": "config"}
        existing.status = "inactive"
        mock_db.query.return_value.filter.return_value.first.return_value = existing
        tenant_id = uuid4()

        result = upsert_channel(mock_db, tenant_id, "whatsapp", {"new": "config"}, "active")

        assert result is existing
        assert existing.config == {"new": "config"}
        assert existing.status == "active"
        mock_db.add.assert_not_called()

    def test_get_channel_found(self, mock_db):
        cfg = MagicMock(spec=ChannelConfig)
        cfg.channel_type = "whatsapp"
        mock_db.query.return_value.filter.return_value.first.return_value = cfg

        result = get_channel(mock_db, uuid4(), "whatsapp")

        assert result is cfg

    def test_get_channel_not_found(self, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = get_channel(mock_db, uuid4(), "whatsapp")

        assert result is None

    def test_delete_channel_existing(self, mock_db):
        cfg = MagicMock(spec=ChannelConfig)
        mock_db.query.return_value.filter.return_value.first.return_value = cfg

        result = delete_channel(mock_db, uuid4(), "whatsapp")

        assert result is True
        mock_db.delete.assert_called_once_with(cfg)
        mock_db.commit.assert_not_called()

    def test_delete_channel_not_found(self, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = delete_channel(mock_db, uuid4(), "whatsapp")

        assert result is False
        mock_db.delete.assert_not_called()
        mock_db.commit.assert_not_called()

    def test_list_all_configs_empty(self, mock_db):
        mock_db.query.return_value.filter.return_value.all.return_value = []

        result = list_all_configs(mock_db, uuid4())

        assert len(result) == 2
        by_type = {r["channel_type"]: r for r in result}
        assert by_type["web_widget"]["status"] == "not_configured"
        assert by_type["whatsapp"]["status"] == "not_configured"

    def test_list_all_configs_with_whatsapp(self, mock_db):
        from datetime import datetime
        cfg = ChannelConfig(
            tenant_id=uuid4(),
            channel_type="whatsapp",
            config={"phone_number_id": "123", "access_token": "secret"},
            status="active",
        )
        cfg.created_at = datetime(2025, 1, 1)
        cfg.updated_at = datetime(2025, 1, 2)
        mock_db.query.return_value.filter.return_value.all.return_value = [cfg]

        result = list_all_configs(mock_db, uuid4())

        assert len(result) == 2
        whatsapp = [r for r in result if r["channel_type"] == "whatsapp"][0]
        assert whatsapp["status"] == "active"
        assert whatsapp["config_mask"]["phone_number_id"] == "123"
        assert whatsapp["config_mask"]["access_token"] == "••••••••"
        assert whatsapp["label"] == "WhatsApp"
        assert whatsapp["description"] != ""

    def test_upsert_invalidates_cache(self, mock_db):
        mock_db.query.return_value.filter.return_value.first.return_value = None
        from app.channels.registry import channel_cache
        channel_cache._built = True

        upsert_channel(mock_db, uuid4(), "whatsapp", {}, "active")

        assert channel_cache._built is False

    def test_delete_invalidates_cache(self, mock_db):
        cfg = MagicMock(spec=ChannelConfig)
        mock_db.query.return_value.filter.return_value.first.return_value = cfg
        from app.channels.registry import channel_cache
        channel_cache._built = True

        delete_channel(mock_db, uuid4(), "whatsapp")

        assert channel_cache._built is False
