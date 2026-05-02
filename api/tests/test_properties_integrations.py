"""Property-based tests for integrations upgrade."""
from __future__ import annotations

import sys
import uuid
from datetime import datetime

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import Column, DateTime, String, Text, Boolean, JSON, create_engine
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Session, declarative_base

from api.app.crypto import decrypt, encrypt

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


def _make_db():
    engine = create_engine("sqlite:///:memory:")
    TestBase.metadata.create_all(engine)
    return Session(engine, autoflush=False)


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


# Feature: integrations-upgrade, Property 1: Credential encryption round-trip
@given(st.dictionaries(st.text(min_size=1), st.text()))
@settings(max_examples=100)
def test_credential_encryption_round_trip(creds):
    plaintext = str(creds)
    ciphertext = encrypt(plaintext)
    assert decrypt(ciphertext) == plaintext
    assert ciphertext != plaintext


# Feature: integrations-upgrade, Property 4: Tool auto-provisioning on connect
@given(st.sampled_from(["shopify", "woocommerce", "stripe"]))
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_provision_creates_expected_tools(provider):
    registry = _get_registry()
    db = _make_db()
    try:
        tenant_id = uuid.uuid4()
        tools = registry.provision_tools(db, tenant_id, provider)
        spec_names = {s["name"] for s in registry.TOOL_SPECS[provider]}
        created_names = {t.name for t in tools}
        assert created_names == spec_names
        assert all(t.enabled for t in tools)
        assert all(t.tenant_id == tenant_id for t in tools)
    finally:
        db.close()


# Feature: integrations-upgrade, Property 5: Tool deprovisioning round-trip
@given(st.sampled_from(["shopify", "woocommerce", "stripe"]))
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_deprovision_removes_all_tools(provider):
    registry = _get_registry()
    db = _make_db()
    try:
        tenant_id = uuid.uuid4()
        registry.provision_tools(db, tenant_id, provider)
        registry.deprovision_tools(db, tenant_id, provider)
        remaining = db.query(TestAgentTool).filter_by(tenant_id=tenant_id).count()
        assert remaining == 0
    finally:
        db.close()


# Feature: integrations-upgrade, Property 11: Primary identifier controls tool call arguments
@given(
    identifier_mode=st.sampled_from(["email", "user_id", "custom"]),
    user_id=st.text(min_size=1),
    extra_field_value=st.text(min_size=1),
)
@settings(max_examples=100)
def test_primary_identifier_controls_lookup_key(identifier_mode, user_id, extra_field_value):
    from api.app.models import CRMConfig
    from api.app.crm import resolve_identifier

    cfg = CRMConfig(tenant_id=uuid.uuid4(), primary_identifier=identifier_mode)
    if identifier_mode == "custom":
        cfg.capabilities = {"identifier_field": "custom_id"}
        extra = {"custom_id": extra_field_value}
    else:
        extra = None

    result = resolve_identifier(cfg, user_id, extra)

    if identifier_mode == "email":
        assert result == user_id
    elif identifier_mode == "user_id":
        assert result == user_id
    else:
        assert result == extra_field_value


# Feature: integrations-upgrade, Property 12: Widget extra_fields propagate to CRM lookup
@given(
    field_name=st.text(alphabet=st.characters(min_codepoint=97, max_codepoint=122), min_size=1, max_size=20),
    field_value=st.text(min_size=1, max_size=100),
    user_id=st.text(alphabet=st.characters(min_codepoint=97, max_codepoint=122), min_size=1, max_size=20),
)
@settings(max_examples=50)
def test_widget_extra_fields_propagate_to_crm_lookup(field_name, field_value, user_id):
    """Property: when primary_identifier='custom' and identifier_field matches an extra_field,
    the extra_field value is used as the CRM lookup key."""
    from api.app.models import CRMConfig
    from api.app.crm import resolve_identifier

    cfg = CRMConfig(
        tenant_id=uuid.uuid4(),
        primary_identifier="custom",
        capabilities={"identifier_field": field_name},
    )
    extra_fields = {field_name: field_value, "other": "ignored"}

    result = resolve_identifier(cfg, user_id, extra_fields)

    assert result == field_value
