"""Telegram channel adapter.

Uses Telegram Bot API via webhook mode.
Bot is created via @BotFather → token is stored in ChannelConfig.config["bot_token"].

Inbound: POST /channels/telegram/webhook → normalize → agent.run() → reply
Outbound: send_message() via Bot API sendMessage
"""
from __future__ import annotations

import httpx
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import ChannelConfig, ChatLog, Tenant
from ..routes_chat import _simple_llm_response


TELEGRAM_API = "https://api.telegram.org/bot{token}"


def _api_url(token: str, method: str) -> str:
    return f"{TELEGRAM_API.format(token=token)}/{method}"


def _resolve_tenant(db: Session, chat_id: int, bot_token: str) -> Tenant | None:
    """Find the tenant that owns this chat_id using the channel lookup cache (O(1))."""
    from .registry import channel_cache

    tenant_id = channel_cache.get_tenant_by_token(bot_token)
    if tenant_id:
        return db.get(Tenant, tenant_id)
    return None


def _get_me(token: str) -> dict | None:
    """Verify bot token and return bot info."""
    import urllib.request
    import json
    url = _api_url(token, "getMe")
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
            return data.get("result") if data.get("ok") else None
    except Exception:
        return None


def set_webhook(token: str, webhook_url: str) -> dict:
    """Set the webhook URL for the bot."""
    import urllib.request
    import json
    url = _api_url(token, "setWebhook")
    payload = json.dumps({"url": webhook_url}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def delete_webhook(token: str) -> dict:
    import urllib.request
    import json
    url = _api_url(token, "deleteWebhook")
    req = urllib.request.Request(url, data=b"", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


async def send_message(token: str, chat_id: str | int, text: str) -> dict:
    """Send a message via Telegram Bot API."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            _api_url(token, "sendMessage"),
            json={"chat_id": int(chat_id) if isinstance(chat_id, str) and chat_id.isdigit() else chat_id, "text": text, "parse_mode": "Markdown"},
        )
        r.raise_for_status()
        return r.json()


def validate_token(token: str) -> tuple[bool, str]:
    """Check if a bot token is valid."""
    me = _get_me(token)
    if me:
        return True, f"Bot @{me.get('username', 'unknown')}"
    return False, "Invalid token or bot unreachable"


async def handle_webhook(update: dict, bot_token_prefix: str = "") -> dict:
    """Process an incoming Telegram webhook update.

    Args:
        update: Telegram webhook payload
        bot_token_prefix: Bot token or prefix from webhook URL path

    Returns dict with status info. Handles messages only (not edits, callbacks, etc).
    """
    message = update.get("message")
    if not message:
        return {"ok": False, "reason": "no_message"}

    chat_id = message["chat"]["id"]
    user_id = str(message["from"]["id"])
    text = message.get("text", "")

    if not text:
        return {"ok": False, "reason": "empty_text"}

    db: Session = SessionLocal()
    try:
        bot_token = ""
        if bot_token_prefix:
            from .registry import channel_cache
            bot_token = channel_cache.get_full_token(bot_token_prefix) or bot_token_prefix

        tenant = _resolve_tenant(db, chat_id, bot_token) if bot_token else None
        if not tenant:
            return {"ok": False, "reason": "tenant_not_found"}
        billing.enforce(tenant)

        cfg = (
            db.query(ChannelConfig)
            .filter(
                ChannelConfig.tenant_id == tenant.id,
                ChannelConfig.channel_type == "telegram",
            )
            .first()
        )
        if not cfg:
            return {"ok": False, "reason": "channel_not_configured"}

        bot_token = cfg.config.get("bot_token", "")

        import uuid
        session_id = uuid.uuid4()

        log = ChatLog(
            tenant_id=tenant.id,
            user_id=user_id,
            direction="incoming",
            message=text,
            session_id=session_id,
            channel="telegram",
        )
        db.add(log)
        db.commit()

        result = await agent.run(db, tenant.id, user_id, text, session_id=session_id, extra_fields={"channel": "telegram"})

        log.response = result["response"]
        log.resolution = "escalated" if result["escalated"] else "resolved"
        log.action_called = result["action_called"]
        log.latency_ms = result["latency_ms"]
        log.sources = result.get("sources") or []
        log.session_id = result.get("session_id")
        tenant.dialogs_used += 1
        if not result["escalated"]:
            tenant.resolved_count += 1
        db.commit()

        if result["response"]:
            await send_message(bot_token, chat_id, result["response"])

        return {"ok": True, "session_id": str(session_id)}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        db.close()
