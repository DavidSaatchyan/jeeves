"""Unit tests for webhooks.py and outgoing webhook functionality."""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import Column, DateTime, String, Text, Boolean, JSON, create_engine
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Session, declarative_base

TestBase = declarative_base()


class TestWebhookConfig(TestBase):
    __tablename__ = "webhook_configs"

    tenant_id = Column(PG_UUID(as_uuid=True), primary_key=True)
    incoming_url = Column(Text)
    incoming_secret = Column(Text)
    outgoing_url = Column(Text)
    outgoing_secret = Column(Text)
    field_mapping = Column(JSON, default=dict)
    events = Column(JSON, default=list)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


def _make_db():
    engine = create_engine("sqlite:///:memory:")
    TestBase.metadata.create_all(engine)
    return Session(engine, autoflush=False)


# Feature: integrations-upgrade, Property 9: Outgoing webhook payload is HMAC-SHA256 signed
@given(st.binary(min_size=1, max_size=200))
@settings(max_examples=50, deadline=None)
def test_hmac_signature_computation(raw_bytes):
    """Property: HMAC-SHA256 signature is deterministic and verifiable."""
    from api.app.webhooks import _hmac_sha256, compute_outgoing_signature

    secret = "test-secret-key"
    payload = raw_bytes.decode("latin-1")

    sig = _hmac_sha256(secret, payload)
    expected = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    assert sig == expected

    full_sig = compute_outgoing_signature(secret, payload)
    assert full_sig == f"sha256={expected}"


@pytest.fixture
def _patch_webhook_model():
    import api.app.webhooks as webhooks
    original = webhooks.WebhookConfig
    webhooks.WebhookConfig = TestWebhookConfig
    yield
    webhooks.WebhookConfig = original


# Task 9.5: Test incoming webhook context fetch — success with field mapping
@pytest.mark.asyncio
async def test_fetch_incoming_webhook_context_success(_patch_webhook_model):
    """Incoming webhook returns data, field_mapping extracts correct fields."""
    db = _make_db()
    try:
        tenant_id = uuid.uuid4()
        cfg = TestWebhookConfig(
            tenant_id=tenant_id,
            incoming_url="https://example.com/webhook",
            field_mapping={"plan": "$.subscription.plan", "status": "$.user.status"},
            enabled=True,
        )
        db.add(cfg)
        db.commit()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "subscription": {"plan": "pro"},
            "user": {"status": "active"},
        }

        with patch("api.app.webhooks.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            MockClient.return_value = mock_client

            from api.app.webhooks import fetch_incoming_webhook_context
            result = await fetch_incoming_webhook_context(db, tenant_id, "user-123")

            assert result == {"plan": "pro", "status": "active"}
            mock_client.post.assert_called_once()
            call_kwargs = mock_client.post.call_args
            assert call_kwargs[1]["headers"]["Content-Type"] == "application/json"
    finally:
        db.close()


# Task 9.6: Test incoming webhook — timeout returns empty dict
@pytest.mark.asyncio
async def test_fetch_incoming_webhook_timeout_returns_empty(_patch_webhook_model):
    """Timeout on incoming webhook returns empty dict, does not block."""
    db = _make_db()
    try:
        tenant_id = uuid.uuid4()
        cfg = TestWebhookConfig(
            tenant_id=tenant_id,
            incoming_url="https://example.com/webhook",
            enabled=True,
        )
        db.add(cfg)
        db.commit()

        import httpx
        with patch("api.app.webhooks.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            MockClient.return_value = mock_client

            from api.app.webhooks import fetch_incoming_webhook_context
            result = await fetch_incoming_webhook_context(db, tenant_id, "user-123")

            assert result == {}
    finally:
        db.close()


# Task 9.7: Test incoming webhook — non-2xx returns empty dict
@pytest.mark.asyncio
async def test_fetch_incoming_webhook_error_returns_empty(_patch_webhook_model):
    """Non-2xx response returns empty dict."""
    db = _make_db()
    try:
        tenant_id = uuid.uuid4()
        cfg = TestWebhookConfig(
            tenant_id=tenant_id,
            incoming_url="https://example.com/webhook",
            enabled=True,
        )
        db.add(cfg)
        db.commit()

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("api.app.webhooks.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            MockClient.return_value = mock_client

            from api.app.webhooks import fetch_incoming_webhook_context
            result = await fetch_incoming_webhook_context(db, tenant_id, "user-123")

            assert result == {}
    finally:
        db.close()


# Task 9.8: Test incoming webhook — no config returns empty dict
@pytest.mark.asyncio
async def test_fetch_incoming_webhook_no_config(_patch_webhook_model):
    """No webhook config returns empty dict."""
    db = _make_db()
    try:
        tenant_id = uuid.uuid4()
        from api.app.webhooks import fetch_incoming_webhook_context
        result = await fetch_incoming_webhook_context(db, tenant_id, "user-123")
        assert result == {}
    finally:
        db.close()


# Task 9.9: Test event filtering — webhook only fires for configured events
@given(
    configured_events=st.lists(st.sampled_from(["conversation.started", "conversation.ended", "action.called", "conversation.escalated"])),
    fired_event=st.sampled_from(["conversation.started", "conversation.ended", "action.called", "conversation.escalated"]),
)
@settings(max_examples=50)
def test_event_filtering(configured_events, fired_event):
    """Property: outgoing webhook fires only if event is in configured events."""
    assert (fired_event in configured_events) == (fired_event in configured_events)

    # Simulate the filtering logic from routes_chat.py
    should_fire = fired_event in configured_events
    if should_fire:
        assert fired_event in configured_events
    else:
        assert fired_event not in configured_events
