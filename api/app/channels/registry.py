"""Channel registry — manages which channels are active per tenant.

Provides a lookup cache indexed by channel identifiers (bot_token, phone_number)
for O(1) webhook routing instead of scanning all active configs.
"""
from __future__ import annotations

import threading
from sqlalchemy.orm import Session

from ..models import ChannelConfig

SUPPORTED_CHANNELS = {"web_widget", "whatsapp"}

CHANNEL_LABELS = {
    "web_widget": "Website Widget",
    "whatsapp": "WhatsApp",
}

CHANNEL_DESCRIPTIONS = {
    "web_widget": "Chat widget embedded on your website",
    "whatsapp": "WhatsApp Business Cloud API — requires Meta developer account",
}


class _ChannelLookupCache:
    """Thread-safe cache for O(1) channel lookup by identifier (bot_token, phone_number).

    Built once on startup, invalidated on config changes.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._token_to_tenant: dict[str, int] = {}
        self._phone_to_tenant: dict[str, int] = {}
        self._built = False

    def build(self, db: Session) -> None:
        with self._lock:
            configs = (
                db.query(ChannelConfig)
                .filter(ChannelConfig.status == "active")
                .all()
            )
            self._token_to_tenant.clear()
            self._phone_to_tenant.clear()
            for cfg in configs:
                if cfg.channel_type == "whatsapp":
                    phone = cfg.config.get("business_phone", "")
                    if phone:
                        self._phone_to_tenant[phone] = cfg.tenant_id
            self._built = True

    def invalidate(self) -> None:
        with self._lock:
            self._built = False

    def get_tenant_by_token(self, token: str) -> int | None:
        if not self._built:
            return None
        return self._token_to_tenant.get(token)

    def get_tenant_by_phone(self, phone: str) -> int | None:
        if not self._built:
            return None
        return self._phone_to_tenant.get(phone)


channel_cache = _ChannelLookupCache()


def build_channel_cache(db: Session) -> None:
    """Build the channel lookup cache. Call on startup or after config changes."""
    channel_cache.build(db)


def get_channels(db: Session, tenant_id) -> list[ChannelConfig]:
    return (
        db.query(ChannelConfig)
        .filter(ChannelConfig.tenant_id == tenant_id)
        .all()
    )


def get_channel(db: Session, tenant_id, channel_type: str) -> ChannelConfig | None:
    return (
        db.query(ChannelConfig)
        .filter(
            ChannelConfig.tenant_id == tenant_id,
            ChannelConfig.channel_type == channel_type,
        )
        .first()
    )


def upsert_channel(
    db: Session,
    tenant_id,
    channel_type: str,
    config: dict,
    status: str = "inactive",
) -> ChannelConfig:
    cfg = get_channel(db, tenant_id, channel_type)
    if cfg:
        cfg.config = config
        cfg.status = status
    else:
        cfg = ChannelConfig(
            tenant_id=tenant_id,
            channel_type=channel_type,
            config=config,
            status=status,
        )
        db.add(cfg)
    channel_cache.invalidate()
    return cfg


def delete_channel(db: Session, tenant_id, channel_type: str) -> bool:
    cfg = get_channel(db, tenant_id, channel_type)
    if not cfg:
        return False
    db.delete(cfg)
    channel_cache.invalidate()
    return True


def list_all_configs(db: Session, tenant_id) -> list[dict]:
    """Return status of all supported channels for a tenant."""
    rows = get_channels(db, tenant_id)
    existing = {r.channel_type: r for r in rows}
    result = []
    for ch_type in SUPPORTED_CHANNELS:
        cfg = existing.get(ch_type)
        result.append({
            "channel_type": ch_type,
            "label": CHANNEL_LABELS.get(ch_type, ch_type),
            "description": CHANNEL_DESCRIPTIONS.get(ch_type, ""),
            "status": cfg.status if cfg else "not_configured",
            "config_mask": _mask_config(cfg.config) if cfg and cfg.config else {},
            "last_error": cfg.last_error if cfg else None,
            "created_at": cfg.created_at.isoformat() if cfg and cfg.created_at else None,
            "updated_at": cfg.updated_at.isoformat() if cfg and cfg.updated_at else None,
        })
    return result


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
