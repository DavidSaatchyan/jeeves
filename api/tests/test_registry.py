"""Unit tests for connectors/registry.py."""
from __future__ import annotations

import sys
import uuid
from datetime import datetime

import pytest
from sqlalchemy import Column, DateTime, String, Text, Boolean, JSON, create_engine
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Session, declarative_base

TestBase = declarative_base()


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


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    TestBase.metadata.create_all(engine)
    session = Session(engine, autoflush=False)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def tenant_id():
    return uuid.uuid4()


@pytest.fixture(autouse=True)
def _patch_registry_model():
    """Swap AgentTool import in registry module for test-friendly version."""
    import api.app.connectors.registry as registry
    original = registry.AgentTool
    registry.AgentTool = TestAgentTool
    yield
    registry.AgentTool = original


def _get_registry():
    import api.app.connectors.registry as registry
    return registry


def test_provision_shopify_creates_all_tools(db, tenant_id):
    registry = _get_registry()
    tools = registry.provision_tools(db, tenant_id, "shopify")
    assert len(tools) == len(registry.TOOL_SPECS["shopify"])
    names = {t.name for t in tools}
    for spec in registry.TOOL_SPECS["shopify"]:
        assert spec["name"] in names


def test_provision_woocommerce_creates_all_tools(db, tenant_id):
    registry = _get_registry()
    tools = registry.provision_tools(db, tenant_id, "woocommerce")
    assert len(tools) == len(registry.TOOL_SPECS["woocommerce"])
    names = {t.name for t in tools}
    for spec in registry.TOOL_SPECS["woocommerce"]:
        assert spec["name"] in names


def test_provision_stripe_creates_all_tools(db, tenant_id):
    registry = _get_registry()
    tools = registry.provision_tools(db, tenant_id, "stripe")
    assert len(tools) == len(registry.TOOL_SPECS["stripe"])
    names = {t.name for t in tools}
    for spec in registry.TOOL_SPECS["stripe"]:
        assert spec["name"] in names


def test_provision_tools_are_enabled(db, tenant_id):
    registry = _get_registry()
    for provider in registry.TOOL_SPECS:
        tools = registry.provision_tools(db, tenant_id, provider)
        for tool in tools:
            assert tool.enabled is True


def test_provision_tools_correct_tenant(db):
    registry = _get_registry()
    t1 = uuid.uuid4()
    t2 = uuid.uuid4()
    registry.provision_tools(db, t1, "shopify")
    registry.provision_tools(db, t2, "stripe")

    shopify_tools = db.query(TestAgentTool).filter_by(tenant_id=t1).all()
    assert all(t.name.startswith("shopify_") for t in shopify_tools)

    stripe_tools = db.query(TestAgentTool).filter_by(tenant_id=t2).all()
    assert all(t.name.startswith("stripe_") for t in stripe_tools)


def test_provision_unknown_provider_raises(db, tenant_id):
    registry = _get_registry()
    with pytest.raises(ValueError, match="Unknown provider"):
        registry.provision_tools(db, tenant_id, "nonexistent")


def test_provision_is_idempotent(db, tenant_id):
    registry = _get_registry()
    registry.provision_tools(db, tenant_id, "shopify")
    registry.provision_tools(db, tenant_id, "shopify")
    count = db.query(TestAgentTool).filter_by(tenant_id=tenant_id).count()
    assert count == len(registry.TOOL_SPECS["shopify"]) * 2


def test_deprovision_removes_all_tools(db, tenant_id):
    registry = _get_registry()
    registry.provision_tools(db, tenant_id, "shopify")
    registry.deprovision_tools(db, tenant_id, "shopify")
    count = db.query(TestAgentTool).filter_by(tenant_id=tenant_id).count()
    assert count == 0


def test_deprovision_does_not_affect_other_providers(db, tenant_id):
    registry = _get_registry()
    registry.provision_tools(db, tenant_id, "shopify")
    registry.provision_tools(db, tenant_id, "stripe")
    registry.deprovision_tools(db, tenant_id, "shopify")

    remaining = db.query(TestAgentTool).filter_by(tenant_id=tenant_id).all()
    assert len(remaining) == len(registry.TOOL_SPECS["stripe"])
    assert all(t.name.startswith("stripe_") for t in remaining)


def test_deprovision_does_not_affect_other_tenants(db):
    registry = _get_registry()
    t1 = uuid.uuid4()
    t2 = uuid.uuid4()
    registry.provision_tools(db, t1, "shopify")
    registry.provision_tools(db, t2, "shopify")
    registry.deprovision_tools(db, t1, "shopify")

    t1_count = db.query(TestAgentTool).filter_by(tenant_id=t1).count()
    t2_count = db.query(TestAgentTool).filter_by(tenant_id=t2).count()
    assert t1_count == 0
    assert t2_count == len(registry.TOOL_SPECS["shopify"])


def test_deprovision_unknown_provider_is_noop(db, tenant_id):
    registry = _get_registry()
    registry.provision_tools(db, tenant_id, "shopify")
    registry.deprovision_tools(db, tenant_id, "nonexistent")
    count = db.query(TestAgentTool).filter_by(tenant_id=tenant_id).count()
    assert count == len(registry.TOOL_SPECS["shopify"])


def test_provision_rollback_on_failure(db, tenant_id, monkeypatch):
    registry = _get_registry()
    original_flush = db.flush

    def failing_flush(*args, **kwargs):
        raise Exception("simulated failure")

    monkeypatch.setattr(db, "flush", failing_flush)

    with pytest.raises(Exception, match="simulated failure"):
        registry.provision_tools(db, tenant_id, "shopify")

    count = db.query(TestAgentTool).filter_by(tenant_id=tenant_id).count()
    assert count == 0
