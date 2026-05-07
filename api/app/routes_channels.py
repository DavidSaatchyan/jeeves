"""Channel management endpoints: config CRUD, webhook handlers, test."""
from __future__ import annotations

import hashlib
import hmac
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .auth import get_current_tenant
from .channels import registry
from .channels import telegram as tg
from .channels import whatsapp as wa
from .db import SessionLocal, get_db
from .models import ChannelConfig, Tenant
from .schemas import ChannelConfigIn, ChannelConfigOut

router = APIRouter(prefix="/channels", tags=["channels"])


def _verify_telegram_signature(request: Request, body_bytes: bytes) -> bool:
    """Verify X-Telegram-Bot-Api-Secret-Token header."""
    secret = request.headers.get("x-telegram-bot-api-secret-token", "")
    if not secret:
        return False
    hash_header = request.headers.get("x-telegram-bot-api-signature", "")
    if not hash_header:
        return False
    expected = hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, hash_header)


def _verify_whatsapp_signature(body_bytes: bytes, signature: str, secret: str) -> bool:
    """Verify X-Hub-Signature-256 header for WhatsApp."""
    if not signature.startswith("sha256="):
        return False
    provided = signature[7:]
    expected = hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)

# ─── Admin API: channel config CRUD ─────────────────────────────────────────


@router.get("", response_model=list[ChannelConfigOut])
def list_channels(
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    return registry.list_all_configs(db, tenant.id)


@router.get("/{channel_type}", response_model=ChannelConfigOut)
def get_channel(
    channel_type: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    if channel_type not in registry.SUPPORTED_CHANNELS:
        raise HTTPException(400, f"Unsupported channel: {channel_type}")
    cfg = registry.get_channel(db, tenant.id, channel_type)
    if not cfg:
        return ChannelConfigOut(
            channel_type=channel_type,
            label=registry.CHANNEL_LABELS.get(channel_type, channel_type),
            description=registry.CHANNEL_DESCRIPTIONS.get(channel_type, ""),
            status="not_configured",
            config_mask={},
            last_error=None,
            created_at=None,
            updated_at=None,
        )
    return ChannelConfigOut(
        channel_type=cfg.channel_type,
        label=registry.CHANNEL_LABELS.get(cfg.channel_type, cfg.channel_type),
        description=registry.CHANNEL_DESCRIPTIONS.get(cfg.channel_type, ""),
        status=cfg.status,
        config_mask=registry._mask_config(cfg.config),
        last_error=cfg.last_error,
        created_at=cfg.created_at.isoformat() if cfg.created_at else None,
        updated_at=cfg.updated_at.isoformat() if cfg.updated_at else None,
    )


@router.post("/{channel_type}", response_model=ChannelConfigOut, status_code=201)
def save_channel(
    channel_type: str,
    body: ChannelConfigIn,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    if channel_type not in registry.SUPPORTED_CHANNELS:
        raise HTTPException(400, f"Unsupported channel: {channel_type}")

    if channel_type == "telegram":
        token = body.config.get("bot_token", "")
        if not token:
            raise HTTPException(400, "bot_token is required")
        ok, msg = tg.validate_token(token)
        if not ok:
            raise HTTPException(400, msg)
        status = "active"
    elif channel_type == "whatsapp":
        ok, msg = wa.validate_config(body.config)
        if not ok:
            raise HTTPException(400, msg)
        status = "active"
    else:
        status = "active"

    cfg = registry.upsert_channel(db, tenant.id, channel_type, body.config, status)
    db.commit()
    db.refresh(cfg)

    return ChannelConfigOut(
        channel_type=cfg.channel_type,
        label=registry.CHANNEL_LABELS.get(cfg.channel_type, cfg.channel_type),
        description=registry.CHANNEL_DESCRIPTIONS.get(cfg.channel_type, ""),
        status=cfg.status,
        config_mask=registry._mask_config(cfg.config),
        last_error=cfg.last_error,
        created_at=cfg.created_at.isoformat() if cfg.created_at else None,
        updated_at=cfg.updated_at.isoformat() if cfg.updated_at else None,
    )


@router.delete("/{channel_type}")
def delete_channel(
    channel_type: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    if channel_type not in registry.SUPPORTED_CHANNELS:
        raise HTTPException(400, f"Unsupported channel: {channel_type}")

    cfg = registry.get_channel(db, tenant.id, channel_type)
    if not cfg:
        raise HTTPException(404, f"Channel {channel_type} not configured")

    if channel_type == "telegram" and cfg.config.get("bot_token"):
        try:
            tg.delete_webhook(cfg.config["bot_token"])
        except Exception:
            pass

    registry.delete_channel(db, tenant.id, channel_type)
    db.commit()
    return {"ok": True}


@router.post("/{channel_type}/test")
async def test_channel(
    channel_type: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: Session = Depends(get_db),
):
    cfg = registry.get_channel(db, tenant.id, channel_type)
    if not cfg:
        raise HTTPException(404, f"Channel {channel_type} not configured")

    if channel_type == "telegram":
        token = cfg.config.get("bot_token", "")
        ok, msg = tg.validate_token(token)
        if ok:
            webhook_url = cfg.config.get("webhook_url", "")
            if webhook_url:
                is_localhost = any(x in webhook_url for x in ("localhost", "127.0.0.1", "0.0.0.0"))
                is_http = webhook_url.startswith("http://")
                if is_localhost or is_http:
                    msg += f" · webhook skipped (use ngrok/HTTPS for production: {webhook_url})"
                else:
                    try:
                        tg.set_webhook(token, webhook_url)
                        msg += " · webhook set"
                    except Exception as e:
                        msg += f" · webhook failed: {e}"
        return {"ok": ok, "message": msg}

    elif channel_type == "whatsapp":
        ok, msg = wa.validate_config(cfg.config)
        return {"ok": ok, "message": msg}

    raise HTTPException(400, f"Cannot test channel: {channel_type}")


# ─── Telegram webhook ───────────────────────────────────────────────────────


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    body_bytes = await request.body()
    body = json.loads(body_bytes)
    result = await tg.handle_webhook(body)
    return JSONResponse(content=result)


# ─── WhatsApp webhook ───────────────────────────────────────────────────────


@router.get("/whatsapp/webhook")
def whatsapp_webhook_verify(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_token: str = Query("", alias="hub.verify_token"),
    hub_challenge: str = Query("", alias="hub.challenge"),
):
    verify_token = ""
    db: Session = SessionLocal()
    try:
        configs = db.query(ChannelConfig).filter(
            ChannelConfig.channel_type == "whatsapp",
            ChannelConfig.status == "active",
        ).all()
        for cfg in configs:
            vt = cfg.config.get("verify_token", "")
            if vt:
                verify_token = vt
                break
    finally:
        db.close()

    result = wa.verify_webhook(hub_mode, hub_token, verify_token, hub_challenge)
    if result:
        return JSONResponse(content=int(result))
    raise HTTPException(403, "Verification failed")


@router.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request):
    body_bytes = await request.body()
    body = json.loads(body_bytes)

    # Verify X-Hub-Signature-256 against each active WhatsApp config's app_secret
    signature = request.headers.get("x-hub-signature-256", "")
    if signature:
        db: Session = SessionLocal()
        try:
            configs = db.query(ChannelConfig).filter(
                ChannelConfig.channel_type == "whatsapp",
                ChannelConfig.status == "active",
            ).all()
            verified = False
            for cfg in configs:
                app_secret = cfg.config.get("app_secret", "")
                if app_secret and _verify_whatsapp_signature(body_bytes, signature, app_secret):
                    verified = True
                    break
            if not verified:
                raise HTTPException(403, "Invalid signature")
        finally:
            db.close()

    result = await wa.handle_webhook(body)
    return JSONResponse(content=result)
