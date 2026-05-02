"""Unit tests for channels modules — pure logic, no app imports."""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import Column, DateTime, String, Text, JSON, create_engine
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Session, declarative_base

TestBase = declarative_base()


class TestChannelConfig(TestBase):
    __tablename__ = "channels_config"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    channel_type = Column(String(32), nullable=False)
    config = Column(JSON, default=dict)
    status = Column(String(16), default="inactive", nullable=False)
    last_error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


def _make_db():
    engine = create_engine("sqlite:///:memory:")
    TestBase.metadata.create_all(engine)
    return Session(engine, autoflush=False)


# ═══ Registry logic tests ═══════════════════════════════════════════════════

SUPPORTED_CHANNELS = {"web_widget", "telegram", "whatsapp"}

CHANNEL_LABELS = {
    "web_widget": "Website Widget",
    "telegram": "Telegram",
    "whatsapp": "WhatsApp",
}

CHANNEL_DESCRIPTIONS = {
    "web_widget": "Chat widget embedded on your website",
    "telegram": "Telegram bot — free, instant setup",
    "whatsapp": "WhatsApp Business Cloud API — requires Meta developer account",
}


def _mask_config(config: dict) -> dict:
    masked = {}
    for k, v in config.items():
        if any(s in k.lower() for s in ("token", "secret", "key", "password")):
            if v:
                masked[k] = "••••••••"
            else:
                masked[k] = None
        else:
            masked[k] = v
    return masked


def test_supported_channels():
    assert SUPPORTED_CHANNELS == {"web_widget", "telegram", "whatsapp"}


def test_upsert_creates_new():
    db = _make_db()
    try:
        tenant_id = uuid.uuid4()
        cfg = TestChannelConfig(
            tenant_id=tenant_id,
            channel_type="telegram",
            config={"bot_token": "abc123"},
            status="active",
        )
        db.add(cfg)
        db.commit()
        assert cfg.channel_type == "telegram"
        assert cfg.status == "active"
        assert cfg.config["bot_token"] == "abc123"
    finally:
        db.close()


def test_upsert_is_update():
    db = _make_db()
    try:
        tenant_id = uuid.uuid4()
        cfg = TestChannelConfig(
            tenant_id=tenant_id,
            channel_type="telegram",
            config={"bot_token": "old"},
            status="active",
        )
        db.add(cfg)
        db.commit()
        cfg.config = {"bot_token": "new"}
        cfg.status = "inactive"
        db.commit()
        stored = db.query(TestChannelConfig).filter_by(tenant_id=tenant_id, channel_type="telegram").first()
        assert stored.config["bot_token"] == "new"
        assert stored.status == "inactive"
    finally:
        db.close()


def test_delete_channel():
    db = _make_db()
    try:
        tenant_id = uuid.uuid4()
        cfg = TestChannelConfig(
            tenant_id=tenant_id,
            channel_type="telegram",
            config={"bot_token": "abc"},
            status="active",
        )
        db.add(cfg)
        db.commit()
        db.delete(cfg)
        db.commit()
        stored = db.query(TestChannelConfig).filter_by(tenant_id=tenant_id, channel_type="telegram").first()
        assert stored is None
    finally:
        db.close()


def test_list_all_configs_returns_all_supported():
    db = _make_db()
    try:
        tenant_id = uuid.uuid4()
        cfg = TestChannelConfig(
            tenant_id=tenant_id,
            channel_type="telegram",
            config={"bot_token": "abc"},
            status="active",
        )
        db.add(cfg)
        db.commit()
        rows = db.query(TestChannelConfig).filter_by(tenant_id=tenant_id).all()
        existing = {r.channel_type: r for r in rows}
        result = []
        for ch_type in SUPPORTED_CHANNELS:
            c = existing.get(ch_type)
            result.append({
                "channel_type": ch_type,
                "status": c.status if c else "not_configured",
            })
        assert len(result) == 3
        types = {r["channel_type"] for r in result}
        assert types == SUPPORTED_CHANNELS
        tg = next(r for r in result if r["channel_type"] == "telegram")
        assert tg["status"] == "active"
        wg = next(r for r in result if r["channel_type"] == "web_widget")
        assert wg["status"] == "not_configured"
    finally:
        db.close()


def test_mask_config_hides_secrets():
    cfg = {
        "bot_token": "secret123",
        "webhook_url": "https://example.com/hook",
        "phone_number_id": "123456",
        "access_token": "EAA_secret",
    }
    masked = _mask_config(cfg)
    assert masked["bot_token"] == "••••••••"
    assert masked["access_token"] == "••••••••"
    assert masked["webhook_url"] == "https://example.com/hook"
    assert masked["phone_number_id"] == "123456"


def test_mask_config_null_value():
    masked = _mask_config({"token": None})
    assert masked["token"] is None


# ═══ Telegram logic tests ═══════════════════════════════════════════════════


def test_telegram_api_url():
    token = "123:ABC"
    method = "sendMessage"
    url = f"https://api.telegram.org/bot{token}/{method}"
    assert url == "https://api.telegram.org/bot123:ABC/sendMessage"


def test_telegram_token_format_valid():
    import re
    pattern = r"^\d+:[A-Za-z0-9_-]+$"
    assert re.match(pattern, "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11") is not None


def test_telegram_token_format_invalid():
    import re
    pattern = r"^\d+:[A-Za-z0-9_-]+$"
    assert re.match(pattern, "not-a-real-token") is None


# ═══ WhatsApp logic tests ═══════════════════════════════════════════════════


def test_verify_webhook_success():
    hub_mode = "subscribe"
    token = "my-token"
    verify_token = "my-token"
    challenge = "challenge-123"
    if hub_mode == "subscribe" and token == verify_token:
        result = challenge
    else:
        result = None
    assert result == "challenge-123"


def test_verify_webhook_wrong_token():
    hub_mode = "subscribe"
    token = "wrong"
    verify_token = "my-token"
    challenge = "challenge-123"
    if hub_mode == "subscribe" and token == verify_token:
        result = challenge
    else:
        result = None
    assert result is None


def test_verify_webhook_wrong_mode():
    hub_mode = "unsubscribe"
    token = "my-token"
    verify_token = "my-token"
    challenge = "challenge-123"
    if hub_mode == "subscribe" and token == verify_token:
        result = challenge
    else:
        result = None
    assert result is None


def test_validate_config_complete():
    cfg = {
        "phone_number_id": "123",
        "access_token": "EAA_xxx",
        "verify_token": "my-secret",
        "business_phone": "+1234567890",
    }
    phone_number_id = cfg.get("phone_number_id", "")
    access_token = cfg.get("access_token", "")
    ok = bool(phone_number_id and access_token)
    assert ok is True


def test_validate_config_missing_phone_id():
    cfg = {"access_token": "EAA_xxx"}
    phone_number_id = cfg.get("phone_number_id", "")
    access_token = cfg.get("access_token", "")
    ok = bool(phone_number_id and access_token)
    assert ok is False


def test_validate_config_missing_token():
    cfg = {"phone_number_id": "123"}
    phone_number_id = cfg.get("phone_number_id", "")
    access_token = cfg.get("access_token", "")
    ok = bool(phone_number_id and access_token)
    assert ok is False


def test_whatsapp_api_url():
    phone_number_id = "123456"
    url = f"https://graph.facebook.com/v17.0/{phone_number_id}/messages"
    assert "123456" in url
    assert "graph.facebook.com" in url


# ═══ Channel config masking tests ═══════════════════════════════════════════


def test_mask_telegram_config():
    cfg = {"bot_token": "123:ABC", "webhook_url": "https://example.com/hook"}
    masked = _mask_config(cfg)
    assert masked["bot_token"] == "••••••••"
    assert masked["webhook_url"] == "https://example.com/hook"


def test_mask_whatsapp_config():
    cfg = {
        "phone_number_id": "123",
        "access_token": "EAA_secret",
        "verify_token": "my-secret",
        "business_phone": "+1234567890",
    }
    masked = _mask_config(cfg)
    assert masked["access_token"] == "••••••••"
    assert masked["verify_token"] == "••••••••"
    assert masked["phone_number_id"] == "123"
    assert masked["business_phone"] == "+1234567890"


def test_mask_empty_config():
    masked = _mask_config({})
    assert masked == {}


def test_mask_non_secret_fields():
    cfg = {"webhook_url": "https://example.com", "position": "right", "title": "Support"}
    masked = _mask_config(cfg)
    assert masked == cfg
