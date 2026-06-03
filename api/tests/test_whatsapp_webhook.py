"""Tests for WhatsApp webhook endpoints (GET verify, POST inbound)."""
from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agents.service import ProcessMessageResult
from app.models import ChannelConfig


@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)


@pytest.fixture
def mock_tenant():
    t = MagicMock()
    t.id = uuid4()
    t.name = "test"
    t.dialogs_used = 0
    t.resolved_count = 0
    return t


@pytest.fixture
def sample_channel_config(mock_tenant):
    cfg = MagicMock(spec=ChannelConfig)
    cfg.tenant_id = mock_tenant.id
    cfg.channel_type = "whatsapp"
    cfg.status = "active"
    cfg.config = {
        "verify_token": "test_verify_token",
        "phone_number_id": "123456789",
        "access_token": "test_access_token",
        "business_phone": "+15551234567",
    }
    return cfg


@pytest.fixture
def override_deps(app, mock_tenant, mock_db):
    from app.db import get_db
    app.dependency_overrides[get_db] = lambda: mock_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client(app, override_deps):
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def mock_webhook_deps(sample_channel_config, mock_tenant):
    """Patch external calls used by the webhook handler — flow goes through process_message."""
    mock_send = AsyncMock(return_value={"messages": [{"id": "wamid.test"}]})
    mock_process = AsyncMock(return_value=ProcessMessageResult(response="ok"))
    mock_resolve = MagicMock(return_value=(mock_tenant, sample_channel_config))

    mocks = {
        "_send_message": mock_send,
        "process_message": mock_process,
        "_resolve_tenant": mock_resolve,
    }

    stack = ExitStack()
    stack.enter_context(patch("app.channels.whatsapp._send_message", mock_send))
    stack.enter_context(patch("app.channels.whatsapp.process_message", mock_process))
    stack.enter_context(patch("app.channels.whatsapp._resolve_tenant", mock_resolve))

    yield mocks
    stack.close()


def _incoming_payload(
    wa_id: str = "+15551112222",
    text: str = "Hello",
    contact_name: str | None = "John Doe",
) -> dict:
    return {
        "entry": [{
            "id": "123",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": "123456789", "display_phone_number": "15551234567"},
                    "contacts": [{"profile": {"name": contact_name}, "wa_id": wa_id}] if contact_name else [],
                    "messages": [{
                        "from": wa_id,
                        "id": "wamid.incoming",
                        "timestamp": "1700000000",
                        "type": "text",
                        "text": {"body": text},
                    }],
                }
            }],
        }],
    }


# ── Webhook Verification (GET) ─────────────────────────────────────────────────────────

class TestVerifyWebhook:
    def test_verify_success(self, client, mock_db, sample_channel_config):
        result = MagicMock()
        result.scalars.return_value.all.return_value = [sample_channel_config]
        mock_db.execute.return_value = result
        mock_db.get.return_value = MagicMock()

        resp = client.get("/channels/whatsapp/webhook", params={
            "hub.mode": "subscribe",
            "hub.verify_token": "test_verify_token",
            "hub.challenge": "1234567890",
        })
        assert resp.status_code == 200
        assert resp.text == "1234567890"

    def test_verify_wrong_token(self, client, mock_db, sample_channel_config):
        result = MagicMock()
        result.scalars.return_value.all.return_value = [sample_channel_config]
        mock_db.execute.return_value = result

        resp = client.get("/channels/whatsapp/webhook", params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_token",
            "hub.challenge": "1234567890",
        })
        assert resp.status_code == 403

    def test_verify_wrong_mode(self, client, mock_db, sample_channel_config):
        result = MagicMock()
        result.scalars.return_value.all.return_value = [sample_channel_config]
        mock_db.execute.return_value = result

        resp = client.get("/channels/whatsapp/webhook", params={
            "hub.mode": "unsubscribe",
            "hub.verify_token": "test_verify_token",
            "hub.challenge": "1234567890",
        })
        assert resp.status_code == 403

    def test_verify_no_active_configs(self, client, mock_db):
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = result

        resp = client.get("/channels/whatsapp/webhook", params={
            "hub.mode": "subscribe",
            "hub.verify_token": "test_verify_token",
            "hub.challenge": "1234567890",
        })
        assert resp.status_code == 403

    def test_verify_missing_query_params(self, client, mock_db, sample_channel_config):
        result = MagicMock()
        result.scalars.return_value.all.return_value = [sample_channel_config]
        mock_db.execute.return_value = result

        resp = client.get("/channels/whatsapp/webhook")
        assert resp.status_code == 403

    def test_verify_multiple_configs_second_matches(self, client, mock_db, mock_tenant):
        cfg1 = MagicMock(spec=ChannelConfig)
        cfg1.tenant_id = mock_tenant.id
        cfg1.config = {"verify_token": "token1", "business_phone": "+1"}
        cfg2 = MagicMock(spec=ChannelConfig)
        cfg2.tenant_id = mock_tenant.id
        cfg2.config = {"verify_token": "token2", "business_phone": "+2"}
        result = MagicMock()
        result.scalars.return_value.all.return_value = [cfg1, cfg2]
        mock_db.execute.return_value = result

        resp = client.get("/channels/whatsapp/webhook", params={
            "hub.mode": "subscribe",
            "hub.verify_token": "token2",
            "hub.challenge": "42",
        })
        assert resp.status_code == 200
        assert resp.text == "42"


# ── Inbound Message Handler (POST) ───────────────────────────────────────────────────────

class TestHandleWebhook:
    def test_inbound_text_message(self, client, mock_db, sample_channel_config, mock_tenant):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_db.get.return_value = mock_tenant

        payload = _incoming_payload()
        resp = client.post("/channels/whatsapp/webhook", json=payload)
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_inbound_calls_send_reply(self, client, mock_db, sample_channel_config, mock_tenant, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_db.get.return_value = mock_tenant

        payload = _incoming_payload()
        resp = client.post("/channels/whatsapp/webhook", json=payload)

        assert resp.status_code == 200
        mock_webhook_deps["process_message"].assert_awaited_once()
        mock_webhook_deps["_send_message"].assert_awaited_once()

    def test_inbound_non_text_message_skipped(self, client, mock_db, sample_channel_config, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]

        payload = _incoming_payload(text="image")
        payload["entry"][0]["changes"][0]["value"]["messages"][0]["type"] = "image"
        del payload["entry"][0]["changes"][0]["value"]["messages"][0]["text"]

        resp = client.post("/channels/whatsapp/webhook", json=payload)
        assert resp.status_code == 200
        mock_webhook_deps["process_message"].assert_not_awaited()
        mock_webhook_deps["_send_message"].assert_not_awaited()

    def test_inbound_no_matching_tenant(self, client, mock_db, mock_webhook_deps):
        mock_webhook_deps["_resolve_tenant"].return_value = (None, None)

        payload = _incoming_payload()
        resp = client.post("/channels/whatsapp/webhook", json=payload)
        assert resp.status_code == 200
        mock_webhook_deps["process_message"].assert_not_awaited()

    def test_inbound_rate_limited(self, client, mock_db, sample_channel_config, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_webhook_deps["process_message"].return_value = ProcessMessageResult(rate_limited=True)

        payload = _incoming_payload()
        resp = client.post("/channels/whatsapp/webhook", json=payload)
        assert resp.status_code == 200

    def test_inbound_moderation_flagged(self, client, mock_db, sample_channel_config, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_webhook_deps["process_message"].return_value = ProcessMessageResult(blocked=True, block_reason="keyword_match")

        payload = _incoming_payload(text="bad content")
        resp = client.post("/channels/whatsapp/webhook", json=payload)
        assert resp.status_code == 200

    def test_inbound_opt_in_keyword(self, client, mock_db, sample_channel_config, mock_tenant, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_db.get.return_value = mock_tenant

        payload = _incoming_payload(text="YES")
        resp = client.post("/channels/whatsapp/webhook", json=payload)
        assert resp.status_code == 200
        mock_webhook_deps["process_message"].assert_not_awaited()
        mock_webhook_deps["_send_message"].assert_awaited()

    def test_inbound_opt_in_variants(self, client, mock_db, sample_channel_config, mock_tenant, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_db.get.return_value = mock_tenant

        for keyword in ("OPT-IN", "START", "CONSENT"):
            mock_webhook_deps["_send_message"].reset_mock()
            payload = _incoming_payload(text=keyword)
            resp = client.post("/channels/whatsapp/webhook", json=payload)
            assert resp.status_code == 200
            mock_webhook_deps["_send_message"].assert_awaited()

    def test_inbound_stop_keyword(self, client, mock_db, sample_channel_config, mock_tenant, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_db.get.return_value = mock_tenant

        payload = _incoming_payload(text="STOP")
        resp = client.post("/channels/whatsapp/webhook", json=payload)
        assert resp.status_code == 200
        mock_webhook_deps["process_message"].assert_not_awaited()
        mock_webhook_deps["_send_message"].assert_awaited()

    def test_inbound_stop_variants(self, client, mock_db, sample_channel_config, mock_tenant, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_db.get.return_value = mock_tenant

        for keyword in ("UNSUBSCRIBE", "CANCEL", "OPT-OUT"):
            payload = _incoming_payload(text=keyword)
            resp = client.post("/channels/whatsapp/webhook", json=payload)
            assert resp.status_code == 200
            mock_webhook_deps["process_message"].assert_not_awaited()

    def test_inbound_followup_intent(self, client, mock_db, sample_channel_config, mock_tenant, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_db.get.return_value = mock_tenant

        payload = _incoming_payload(text="I feel great")
        resp = client.post("/channels/whatsapp/webhook", json=payload)
        assert resp.status_code == 200
        mock_webhook_deps["process_message"].assert_awaited_once()

    def test_inbound_campaign_intent(self, client, mock_db, sample_channel_config, mock_tenant, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_db.get.return_value = mock_tenant

        payload = _incoming_payload(text="Great offer")
        resp = client.post("/channels/whatsapp/webhook", json=payload)
        assert resp.status_code == 200
        mock_webhook_deps["process_message"].assert_awaited_once()

    def test_inbound_emergency_intent(self, client, mock_db, sample_channel_config, mock_tenant, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_db.get.return_value = mock_tenant

        payload = _incoming_payload(text="I need help now")
        resp = client.post("/channels/whatsapp/webhook", json=payload)
        assert resp.status_code == 200
        mock_webhook_deps["process_message"].assert_awaited_once()

    def test_inbound_appointment_intent(self, client, mock_db, sample_channel_config, mock_tenant, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_db.get.return_value = mock_tenant

        payload = _incoming_payload(text="book appointment")
        resp = client.post("/channels/whatsapp/webhook", json=payload)
        assert resp.status_code == 200
        mock_webhook_deps["process_message"].assert_awaited_once()

    def test_inbound_general_intent(self, client, mock_db, sample_channel_config, mock_tenant, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_db.get.return_value = mock_tenant

        payload = _incoming_payload(text="What is your return policy?")
        resp = client.post("/channels/whatsapp/webhook", json=payload)
        assert resp.status_code == 200
        mock_webhook_deps["process_message"].assert_awaited_once()

    def test_inbound_escalated_response(self, client, mock_db, sample_channel_config, mock_tenant, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_db.get.return_value = mock_tenant

        payload = _incoming_payload(text="speak to agent")
        resp = client.post("/channels/whatsapp/webhook", json=payload)
        assert resp.status_code == 200

    def test_inbound_empty_response_not_sent(self, client, mock_db, sample_channel_config, mock_tenant, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_db.get.return_value = mock_tenant

        payload = _incoming_payload(text="test")
        resp = client.post("/channels/whatsapp/webhook", json=payload)
        assert resp.status_code == 200

    def test_inbound_empty_payload(self, client, mock_db):
        resp = client.post("/channels/whatsapp/webhook", json={})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_inbound_no_contact_name(self, client, mock_db, sample_channel_config, mock_tenant):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_db.get.return_value = mock_tenant

        payload = _incoming_payload(contact_name=None)
        resp = client.post("/channels/whatsapp/webhook", json=payload)
        assert resp.status_code == 200

    def test_inbound_logs_chatlog(self, client, mock_db, sample_channel_config, mock_tenant, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_db.get.return_value = mock_tenant

        payload = _incoming_payload(text="Hello world")
        resp = client.post("/channels/whatsapp/webhook", json=payload)
        assert resp.status_code == 200
        mock_webhook_deps["process_message"].assert_awaited_once()
