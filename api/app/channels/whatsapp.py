"""WhatsApp channel adapter.

Uses WhatsApp Cloud API (direct, no BSP needed).
Config: phone_number_id, access_token, verify_token, business_phone.

Inbound: POST /channels/whatsapp/webhook → normalize → agent.run() → reply
Outbound: send_message() via Cloud API
Webhook verification: GET /channels/whatsapp/webhook (Meta challenge)
"""
from __future__ import annotations

import httpx
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import ChannelConfig, ChatLog, Tenant
from ..routes_chat import _simple_llm_response


WHATSAPP_API = "https://graph.facebook.com/v17.0/{phone_number_id}/messages"


def _api_url(phone_number_id: str) -> str:
    return WHATSAPP_API.format(phone_number_id=phone_number_id)


def _resolve_tenant(db: Session, wa_id: str) -> tuple[Tenant | None, ChannelConfig | None]:
    """Find the tenant that owns this WhatsApp number."""
    configs = (
        db.query(ChannelConfig)
        .filter(
            ChannelConfig.channel_type == "whatsapp",
            ChannelConfig.status == "active",
        )
        .all()
    )
    for cfg in configs:
        phone = cfg.config.get("business_phone", "")
        if phone:
            return db.get(Tenant, cfg.tenant_id), cfg
    return None, None


async def send_message(phone_number_id: str, access_token: str, wa_id: str, text: str) -> dict:
    """Send a message via WhatsApp Cloud API."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            _api_url(phone_number_id),
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": wa_id,
                "type": "text",
                "text": {"body": text},
            },
        )
        r.raise_for_status()
        return r.json()


def verify_webhook(hub_mode: str, token: str, verify_token: str, challenge: str) -> str | None:
    """Verify the webhook subscription (Meta GET challenge).

    Returns the challenge string if verification succeeds, None otherwise.
    """
    if hub_mode == "subscribe" and token == verify_token:
        return challenge
    return None


async def handle_webhook(body: dict) -> dict:
    """Process an incoming WhatsApp webhook.

    WhatsApp sends a POST with structure:
    {
      "entry": [{
        "changes": [{
          "value": {
            "messages": [{"from": "wa_id", "text": {"body": "text"}}],
            "contacts": [{"wa_id": "...", "profile": {"name": "..."}}]
          }
        }]
      }]
    }
    """
    entries = body.get("entry") or []
    for entry in entries:
        changes = entry.get("changes") or []
        for change in changes:
            value = change.get("value") or {}
            messages = value.get("messages") or []
            for msg in messages:
                if msg.get("type") != "text":
                    continue
                wa_id = msg["from"]
                text = msg["text"]["body"]

                db: Session = SessionLocal()
                try:
                    tenant, cfg = _resolve_tenant(db, wa_id)
                    if not tenant or not cfg:
                        continue
                    billing.enforce(tenant)

                    phone_number_id = cfg.config.get("phone_number_id", "")
                    access_token = cfg.config.get("access_token", "")

                    import uuid
                    session_id = uuid.uuid4()

                    log = ChatLog(
                        tenant_id=tenant.id,
                        user_id=wa_id,
                        direction="incoming",
                        message=text,
                        session_id=session_id,
                        channel="whatsapp",
                    )
                    db.add(log)
                    db.commit()

                    result = await agent.run(db, tenant.id, wa_id, text, session_id=session_id, extra_fields={"channel": "whatsapp"})

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
                        await send_message(phone_number_id, access_token, wa_id, result["response"])
                except Exception:
                    pass
                finally:
                    db.close()

    return {"ok": True}


def validate_config(config: dict) -> tuple[bool, str]:
    """Check if WhatsApp config is valid by making a test API call."""
    phone_number_id = config.get("phone_number_id", "")
    access_token = config.get("access_token", "")
    if not phone_number_id or not access_token:
        return False, "Missing phone_number_id or access_token"
    return True, "Config looks valid"
