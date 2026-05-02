"""Unit tests for identifier substitution in crm.py."""
from __future__ import annotations

import uuid

import pytest
from api.app.crm import resolve_identifier
from api.app.models import CRMConfig


def _make_cfg(primary_identifier: str, identifier_field: str | None = None) -> CRMConfig:
    """Create a CRMConfig with the given primary_identifier."""
    return CRMConfig(
        tenant_id=uuid.uuid4(),
        primary_identifier=primary_identifier,
        capabilities={"identifier_field": identifier_field} if identifier_field else {},
    )


def test_resolve_email_returns_user_id():
    cfg = _make_cfg("email")
    assert resolve_identifier(cfg, "john@example.com") == "john@example.com"


def test_resolve_user_id_returns_user_id():
    cfg = _make_cfg("user_id")
    assert resolve_identifier(cfg, "user-12345") == "user-12345"


def test_resolve_custom_with_extra_fields():
    cfg = _make_cfg("custom", identifier_field="phone")
    assert resolve_identifier(cfg, "ignored", {"phone": "+1234567890"}) == "+1234567890"


def test_resolve_custom_missing_field_falls_back():
    cfg = _make_cfg("custom", identifier_field="phone")
    assert resolve_identifier(cfg, "user-999", {"email": "x@x.com"}) == "user-999"


def test_resolve_custom_no_extra_fields_falls_back():
    cfg = _make_cfg("custom", identifier_field="phone")
    assert resolve_identifier(cfg, "user-999") == "user-999"


def test_resolve_custom_no_identifier_field_falls_back():
    cfg = _make_cfg("custom")
    assert resolve_identifier(cfg, "user-999", {"anything": "value"}) == "user-999"


def test_resolve_none_cfg_defaults_to_email():
    assert resolve_identifier(None, "john@example.com") == "john@example.com"


def test_resolve_custom_field_value_converted_to_string():
    cfg = _make_cfg("custom", identifier_field="order_id")
    assert resolve_identifier(cfg, "ignored", {"order_id": 12345}) == "12345"
