"""Unit tests for routes_integrations.py."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Column, DateTime, String, Text, Boolean, Integer, JSON, create_engine
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Session, declarative_base

from api.app.crypto import encrypt

pytestmark = pytest.mark.skip(reason="Integration tests require Docker with PostgreSQL")

TestBase = declarative_base()


class TestTenant(TestBase):
    __tablename__ = "tenants"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    email = Column(Text, unique=True, nullable=False)
    hashed_password = Column(Text, nullable=False)
    email_verified = Column(Boolean, default=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    dialogs_used = Column(Integer, default=0, nullable=False)
    resolved_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class TestNativeConnector(TestBase):
    __tablename__ = "native_connectors"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    provider = Column(String(32), nullable=False)
    status = Column(String(16), default="connected", nullable=False)
    credentials = Column(Text, nullable=False)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class TestAgentTool(TestBase):
    __tablename__ = "agent_tools"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    name = Column(String(64), nullable=False)
    description = Column(Text, nullable=False)
    tool_type = Column(String(16), nullable=False)
    method = Column(String(8), default="GET", nullable=False)
    url_template = Column(Text, nullable=False)
    headers = Column(JSON, default=dict)
    body_template = Column(JSON, default=dict)
    parameters = Column(JSON, default=dict)
    require_confirmation = Column(Boolean, default=False, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


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


class TestWriteBackConfig(TestBase):
    __tablename__ = "writeback_configs"
    tenant_id = Column(PG_UUID(as_uuid=True), primary_key=True)
    type = Column(String(32), default="off", nullable=False)
    hubspot_note_enabled = Column(Boolean, default=False, nullable=False)
    hubspot_task_on_escalation = Column(Boolean, default=False, nullable=False)
    webhook_url = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestBase.metadata.create_all(engine)
    session = Session(engine, autoflush=False)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def tenant(db):
    t = TestTenant(
        id=uuid.uuid4(),
        name="Test Tenant",
        email="test@example.com",
        hashed_password="hashed",
    )
    db.add(t)
    db.commit()
    return t


@pytest.fixture()
def token(tenant):
    import jwt
    from api.app.config import get_settings
    from datetime import timedelta, datetime
    settings = get_settings()
    payload = {
        "sub": str(tenant.id),
        "kind": "access",
        "iat": int(datetime.utcnow().timestamp()),
        "exp": int((datetime.utcnow() + timedelta(hours=1)).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


import importlib
import sys


@pytest.fixture()
def client(db, token, monkeypatch):
    from fastapi import FastAPI, Depends
    from api.app.auth import get_current_tenant

    # Patch models at the source before importing routes
    import api.app.models as models_mod
    import api.app.connectors.registry as reg_mod

    monkeypatch.setattr(models_mod, "NativeConnector", TestNativeConnector)
    monkeypatch.setattr(models_mod, "WebhookConfig", TestWebhookConfig)
    monkeypatch.setattr(models_mod, "WriteBackConfig", TestWriteBackConfig)
    monkeypatch.setattr(models_mod, "Tenant", TestTenant)
    monkeypatch.setattr(reg_mod, "AgentTool", TestAgentTool)

    # Force reload of routes module to pick up patched models
    if "api.app.routes_integrations" in sys.modules:
        importlib.reload(sys.modules["api.app.routes_integrations"])

    # Import after reload to get the patched module
    from api.app.routes_integrations import router
    from api.app.db import get_db as _get_db

    app = FastAPI()

    def _override_db():
        return db

    def _override_tenant():
        return db.query(TestTenant).first()

    app.include_router(router)
    app.dependency_overrides[_get_db] = _override_db
    app.dependency_overrides[get_current_tenant] = _override_tenant

    yield TestClient(app)


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_list_integrations_empty(client, token):
    r = client.get("/integrations", headers=_headers(token))
    assert r.status_code == 200
    data = r.json()
    assert data["native_connectors"] == []
    assert data["webhook_config"] is None
    assert data["writeback_config"] is None


def test_connect_shopify_provisions_tools(client, token, db):
    r = client.post(
        "/integrations/native",
        json={
            "provider": "shopify",
            "credentials": {"shop": "test.myshopify.com", "access_token": "shpat_xxx"},
            "meta": {"shop_name": "Test Shop"},
        },
        headers=_headers(token),
    )
    assert r.status_code == 201
    data = r.json()
    assert data["provider"] == "shopify"
    assert data["status"] == "connected"
    assert data["meta"]["shop_name"] == "Test Shop"

    # Verify tools were provisioned
    tools = db.query(TestAgentTool).filter(
        TestAgentTool.tenant_id == db.query(TestTenant).first().id,
        TestAgentTool.name.startswith("shopify_"),
    ).all()
    assert len(tools) == 4
    assert all(t.enabled for t in tools)


def test_connect_missing_credentials(client, token):
    r = client.post(
        "/integrations/native",
        json={"provider": "shopify", "credentials": {"foo": "bar"}, "meta": {}},
        headers=_headers(token),
    )
    assert r.status_code == 400
    assert "Missing credential keys" in r.json()["detail"]


def test_connect_unsupported_provider(client, token):
    r = client.post(
        "/integrations/native",
        json={"provider": "magento", "credentials": {"key": "val"}, "meta": {}},
        headers=_headers(token),
    )
    assert r.status_code == 422


def test_disconnect_native_removes_tools(client, token, db):
    tenant_id = db.query(TestTenant).first().id
    # Create connector directly
    nc = TestNativeConnector(
        tenant_id=tenant_id,
        provider="stripe",
        credentials=encrypt(json.dumps({"secret_key": "sk_test_xxx"})),
    )
    db.add(nc)
    from api.app.connectors.registry import provision_tools
    provision_tools(db, tenant_id, "stripe")
    db.commit()

    r = client.delete("/integrations/native/stripe", headers=_headers(token))
    assert r.status_code == 200
    assert r.json()["ok"] is True

    remaining = db.query(TestNativeConnector).filter_by(tenant_id=tenant_id).all()
    assert len(remaining) == 0

    tool_count = db.query(TestAgentTool).filter(
        TestAgentTool.tenant_id == tenant_id,
        TestAgentTool.name.startswith("stripe_"),
    ).count()
    assert tool_count == 0


def test_disconnect_not_connected(client, token):
    r = client.delete("/integrations/native/woocommerce", headers=_headers(token))
    assert r.status_code == 404


@patch("api.app.routes_integrations._test_connectivity", new_callable=AsyncMock)
async def test_native_connect_success(mock_test, client, token, db):
    mock_test.return_value = True
    tenant_id = db.query(TestTenant).first().id
    nc = TestNativeConnector(
        tenant_id=tenant_id,
        provider="shopify",
        credentials=encrypt(json.dumps({"shop": "test.myshopify.com", "access_token": "shpat_xxx"})),
    )
    db.add(nc)
    db.commit()

    r = client.post("/integrations/native/shopify/test", headers=_headers(token))
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_webhook_config_crud(client, token):
    r = client.get("/integrations/webhook", headers=_headers(token))
    assert r.status_code == 200

    r = client.post(
        "/integrations/webhook",
        json={
            "outgoing_url": "https://example.com/webhook",
            "outgoing_secret": "secret123",
            "events": ["conversation.ended", "conversation.started"],
            "enabled": True,
        },
        headers=_headers(token),
    )
    assert r.status_code == 201
    data = r.json()
    assert data["outgoing_url"] == "https://example.com/webhook"
    assert data["events"] == ["conversation.ended", "conversation.started"]
    assert "secret123" not in str(data)

    r = client.get("/integrations/webhook", headers=_headers(token))
    assert r.status_code == 200
    assert r.json()["outgoing_url"] == "https://example.com/webhook"


def test_writeback_config_crud(client, token):
    r = client.get("/integrations/writeback", headers=_headers(token))
    assert r.status_code == 200
    assert r.json()["type"] == "off"

    r = client.post(
        "/integrations/writeback",
        json={
            "type": "hubspot_note",
            "hubspot_note_enabled": True,
            "hubspot_task_on_escalation": True,
        },
        headers=_headers(token),
    )
    assert r.status_code == 201
    data = r.json()
    assert data["type"] == "hubspot_note"
    assert data["hubspot_note_enabled"] is True

    r = client.get("/integrations/writeback", headers=_headers(token))
    assert r.status_code == 200
    assert r.json()["type"] == "hubspot_note"


def test_list_integrations_shows_connected(client, token, db):
    tenant_id = db.query(TestTenant).first().id
    nc = TestNativeConnector(
        tenant_id=tenant_id,
        provider="woocommerce",
        credentials=encrypt(json.dumps({"base_url": "https://test.com", "consumer_key": "ck", "consumer_secret": "cs"})),
    )
    db.add(nc)
    db.commit()

    r = client.get("/integrations", headers=_headers(token))
    assert r.status_code == 200
    data = r.json()
    assert len(data["native_connectors"]) == 1
    assert data["native_connectors"][0]["provider"] == "woocommerce"
