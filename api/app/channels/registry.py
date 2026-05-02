"""Channel registry — manages which channels are active per tenant."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import ChannelConfig

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
    return cfg


def delete_channel(db: Session, tenant_id, channel_type: str) -> bool:
    cfg = get_channel(db, tenant_id, channel_type)
    if not cfg:
        return False
    db.delete(cfg)
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
