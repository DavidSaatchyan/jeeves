"""Tests for WhatsApp webhook endpoints (GET verify, POST inbound)."""
from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

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
def mock_webhook_deps():
    """Patch all external calls used by the webhook handler."""
    mock_rate_limit = MagicMock(return_value=True)
    mock_moderate = MagicMock(return_value=(False, ""))
    mock_classify = AsyncMock(return_value="general_inquiry")
    mock_llm = AsyncMock(return_value={
        "response": "I understand. Let me help you with that.",
        "escalated": False,
        "action_called": "",
        "latency_ms": 85,
    })
    mock_consent = MagicMock()
    mock_create_conv = MagicMock()
    mock_add_msg = MagicMock()
    mock_send = AsyncMock(return_value={"messages": [{"id": "wamid.test"}]})
    mock_history = MagicMock(return_value=[])
    mock_route = AsyncMock()

    mocks = {
        "check_rate_limit": mock_rate_limit,
        "moderate": mock_moderate,
        "classify_intent": mock_classify,
        "simple_llm_response": mock_llm,
        "ConsentManager": mock_consent,
        "get_or_create_conversation": mock_create_conv,
        "add_message": mock_add_msg,
        "_send_message": mock_send,
        "get_conversation_history": mock_history,
        "route_event": mock_route,
    }

    stack = ExitStack()
    stack.enter_context(patch("app.channels.whatsapp.check_rate_limit", mock_rate_limit))
    stack.enter_context(patch("app.channels.whatsapp.moderate", mock_moderate))
    stack.enter_context(patch("app.channels.whatsapp.classify_intent", mock_classify))
    stack.enter_context(patch("app.channels.whatsapp.simple_llm_response", mock_llm))
    stack.enter_context(patch("app.channels.whatsapp.ConsentManager", mock_consent))
    stack.enter_context(patch("app.channels.whatsapp.get_or_create_conversation", mock_create_conv))
    stack.enter_context(patch("app.channels.whatsapp.add_message", mock_add_msg))
    stack.enter_context(patch("app.channels.whatsapp._send_message", mock_send))
    stack.enter_context(patch("app.core.memory.get_conversation_history", mock_history))
    stack.enter_context(patch("app.core.workflows.registry.route_event", mock_route))

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
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_db.get.return_value = MagicMock()

        resp = client.get("/channels/whatsapp/webhook", params={
            "hub.mode": "subscribe",
            "hub.verify_token": "test_verify_token",
            "hub.challenge": "1234567890",
        })
        assert resp.status_code == 200
        assert resp.text == "1234567890"

    def test_verify_wrong_token(self, client, mock_db, sample_channel_config):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]

        resp = client.get("/channels/whatsapp/webhook", params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_token",
            "hub.challenge": "1234567890",
        })
        assert resp.status_code == 403

    def test_verify_wrong_mode(self, client, mock_db, sample_channel_config):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]

        resp = client.get("/channels/whatsapp/webhook", params={
            "hub.mode": "unsubscribe",
            "hub.verify_token": "test_verify_token",
            "hub.challenge": "1234567890",
        })
        assert resp.status_code == 403

    def test_verify_no_active_configs(self, client, mock_db):
        mock_db.query.return_value.filter.return_value.all.return_value = []

        resp = client.get("/channels/whatsapp/webhook", params={
            "hub.mode": "subscribe",
            "hub.verify_token": "test_verify_token",
            "hub.challenge": "1234567890",
        })
        assert resp.status_code == 403

    def test_verify_missing_query_params(self, client, mock_db, sample_channel_config):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]

        resp = client.get("/channels/whatsapp/webhook")
        assert resp.status_code == 403

    def test_verify_multiple_configs_second_matches(self, client, mock_db, mock_tenant):
        cfg1 = MagicMock(spec=ChannelConfig)
        cfg1.tenant_id = mock_tenant.id
        cfg1.config = {"verify_token": "token1", "business_phone": "+1"}
        cfg2 = MagicMock(spec=ChannelConfig)
        cfg2.tenant_id = mock_tenant.id
        cfg2.config = {"verify_token": "token2", "business_phone": "+2"}
        mock_db.query.return_value.filter.return_value.all.return_value = [cfg1, cfg2]

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
        mock_webhook_deps["classify_intent"].assert_awaited()
        mock_webhook_deps["simple_llm_response"].assert_awaited()
        mock_webhook_deps["_send_message"].assert_awaited()
        assert mock_tenant.dialogs_used == 1
        assert mock_tenant.resolved_count == 1

    def test_inbound_non_text_message_skipped(self, client, mock_db, sample_channel_config, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]

        payload = _incoming_payload(text="image")
        payload["entry"][0]["changes"][0]["value"]["messages"][0]["type"] = "image"
        del payload["entry"][0]["changes"][0]["value"]["messages"][0]["text"]

        resp = client.post("/channels/whatsapp/webhook", json=payload)
        assert resp.status_code == 200
        mock_webhook_deps["classify_intent"].assert_not_awaited()
        mock_webhook_deps["_send_message"].assert_not_awaited()

    def test_inbound_no_matching_tenant(self, client, mock_db, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = []

        payload = _incoming_payload()
        resp = client.post("/channels/whatsapp/webhook", json=payload)
        assert resp.status_code == 200
        mock_webhook_deps["classify_intent"].assert_not_awaited()

    def test_inbound_rate_limited(self, client, mock_db, sample_channel_config, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_webhook_deps["check_rate_limit"].return_value = False

        payload = _incoming_payload()
        resp = client.post("/channels/whatsapp/webhook", json=payload)
        assert resp.status_code == 200
        mock_webhook_deps["_send_message"].assert_awaited()
        mock_webhook_deps["classify_intent"].assert_not_awaited()
        call_args = mock_webhook_deps["_send_message"].await_args
        assert call_args is not None
        assert "Too many messages" in call_args[0][3]

    def test_inbound_moderation_flagged(self, client, mock_db, sample_channel_config, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_webhook_deps["moderate"].return_value = (True, "keyword_match")

        payload = _incoming_payload(text="bad content")
        resp = client.post("/channels/whatsapp/webhook", json=payload)
        assert resp.status_code == 200
        mock_webhook_deps["_send_message"].assert_awaited()
        mock_webhook_deps["classify_intent"].assert_not_awaited()

    def test_inbound_opt_in_keyword(self, client, mock_db, sample_channel_config, mock_tenant, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_db.get.return_value = mock_tenant

        payload = _incoming_payload(text="YES")
        resp = client.post("/channels/whatsapp/webhook", json=payload)
        assert resp.status_code == 200
        mock_webhook_deps["ConsentManager"].capture.assert_called_once()
        mock_webhook_deps["classify_intent"].assert_not_awaited()
        mock_webhook_deps["_send_message"].assert_awaited()

    def test_inbound_opt_in_variants(self, client, mock_db, sample_channel_config, mock_tenant, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_db.get.return_value = mock_tenant

        for keyword in ("OPT-IN", "START", "CONSENT"):
            mock_webhook_deps["ConsentManager"].capture.reset_mock()
            payload = _incoming_payload(text=keyword)
            resp = client.post("/channels/whatsapp/webhook", json=payload)
            assert resp.status_code == 200
            mock_webhook_deps["ConsentManager"].capture.assert_called_once()

    def test_inbound_stop_keyword(self, client, mock_db, sample_channel_config, mock_tenant, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_db.get.return_value = mock_tenant

        payload = _incoming_payload(text="STOP")
        resp = client.post("/channels/whatsapp/webhook", json=payload)
        assert resp.status_code == 200
        mock_webhook_deps["classify_intent"].assert_not_awaited()
        mock_webhook_deps["_send_message"].assert_awaited()

    def test_inbound_stop_variants(self, client, mock_db, sample_channel_config, mock_tenant, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_db.get.return_value = mock_tenant

        for keyword in ("UNSUBSCRIBE", "CANCEL", "OPT-OUT"):
            payload = _incoming_payload(text=keyword)
            resp = client.post("/channels/whatsapp/webhook", json=payload)
            assert resp.status_code == 200
            mock_webhook_deps["classify_intent"].assert_not_awaited()

    def test_inbound_followup_intent(self, client, mock_db, sample_channel_config, mock_tenant, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_db.get.return_value = mock_tenant
        mock_webhook_deps["classify_intent"].return_value = "followup_feeling_good"

        payload = _incoming_payload(text="I feel great")
        resp = client.post("/channels/whatsapp/webhook", json=payload)
        assert resp.status_code == 200
        mock_webhook_deps["route_event"].assert_awaited()
        mock_webhook_deps["simple_llm_response"].assert_not_awaited()

    def test_inbound_campaign_intent(self, client, mock_db, sample_channel_config, mock_tenant, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_db.get.return_value = mock_tenant
        mock_webhook_deps["classify_intent"].return_value = "campaign_positive"

        payload = _incoming_payload(text="Great offer")
        resp = client.post("/channels/whatsapp/webhook", json=payload)
        assert resp.status_code == 200
        mock_webhook_deps["route_event"].assert_awaited()
        mock_webhook_deps["simple_llm_response"].assert_not_awaited()

    def test_inbound_emergency_intent(self, client, mock_db, sample_channel_config, mock_tenant, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_db.get.return_value = mock_tenant
        mock_webhook_deps["classify_intent"].return_value = "emergency"

        payload = _incoming_payload(text="I need help now")
        resp = client.post("/channels/whatsapp/webhook", json=payload)
        assert resp.status_code == 200
        mock_webhook_deps["route_event"].assert_awaited()
        mock_webhook_deps["simple_llm_response"].assert_not_awaited()

    def test_inbound_appointment_intent(self, client, mock_db, sample_channel_config, mock_tenant, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_db.get.return_value = mock_tenant

        for intent in ("appointment", "reschedule", "cancel", "availability"):
            mock_webhook_deps["classify_intent"].return_value = intent
            mock_webhook_deps["route_event"].reset_mock()

            payload = _incoming_payload(text="book appointment")
            resp = client.post("/channels/whatsapp/webhook", json=payload)
            assert resp.status_code == 200
            mock_webhook_deps["route_event"].assert_awaited()
            mock_webhook_deps["simple_llm_response"].assert_not_awaited()

    def test_inbound_general_intent(self, client, mock_db, sample_channel_config, mock_tenant, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_db.get.return_value = mock_tenant
        mock_webhook_deps["classify_intent"].return_value = "general_inquiry"

        payload = _incoming_payload(text="What is your return policy?")
        resp = client.post("/channels/whatsapp/webhook", json=payload)
        assert resp.status_code == 200
        mock_webhook_deps["simple_llm_response"].assert_awaited()
        mock_webhook_deps["route_event"].assert_not_awaited()

    def test_inbound_escalated_response(self, client, mock_db, sample_channel_config, mock_tenant, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_db.get.return_value = mock_tenant
        mock_webhook_deps["simple_llm_response"].return_value = {
            "response": "Let me connect you with a human.",
            "escalated": True,
            "action_called": "escalate",
            "latency_ms": 100,
        }

        payload = _incoming_payload(text="speak to agent")
        resp = client.post("/channels/whatsapp/webhook", json=payload)
        assert resp.status_code == 200
        assert mock_tenant.resolved_count == 0
        assert mock_tenant.dialogs_used == 1

    def test_inbound_empty_response_not_sent(self, client, mock_db, sample_channel_config, mock_tenant, mock_webhook_deps):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_db.get.return_value = mock_tenant
        mock_webhook_deps["simple_llm_response"].return_value = {
            "response": "",
            "escalated": False,
            "action_called": "",
            "latency_ms": 50,
        }
        mock_webhook_deps["_send_message"].reset_mock()

        payload = _incoming_payload(text="test")
        resp = client.post("/channels/whatsapp/webhook", json=payload)
        assert resp.status_code == 200
        mock_webhook_deps["_send_message"].assert_not_awaited()

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

    def test_inbound_logs_chatlog(self, client, mock_db, sample_channel_config, mock_tenant):
        mock_db.query.return_value.filter.return_value.all.return_value = [sample_channel_config]
        mock_db.get.return_value = mock_tenant

        payload = _incoming_payload(text="Hello world")
        resp = client.post("/channels/whatsapp/webhook", json=payload)
        assert resp.status_code == 200
        mock_db.add.assert_called()
        added = mock_db.add.call_args[0][0]
        assert added.message == "Hello world"
        assert added.channel == "whatsapp"
        assert added.direction == "incoming"
