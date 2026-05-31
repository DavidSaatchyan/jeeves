"""WhatsApp channel — FastAPI router, webhook receiver, reply sender.

Uses WhatsApp Cloud API (direct, no BSP needed).
Config: phone_number_id, access_token, verify_token, business_phone.

Inbound:  POST /channels/whatsapp/webhook -> verify -> moderate -> AI -> reply
Verify:   GET  /channels/whatsapp/webhook  (Meta challenge)
"""
from __future__ import annotations

import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ChannelConfig, ChatLog, Tenant
from ..shared.inbox_writer import add_message, get_or_create_conversation
from ..core.ai import simple_llm_response
from ..core.compliance.consent import ConsentManager
from ..rate_limit import check_rate_limit
from ..moderation import moderate
from ..core.ai import classify_intent

WHATSAPP_API = "https://graph.facebook.com/v17.0/{phone_number_id}/messages"

router = APIRouter(prefix="/channels/whatsapp", tags=["whatsapp"])


def _api_url(phone_number_id: str) -> str:
    return WHATSAPP_API.format(phone_number_id=phone_number_id)


def _resolve_tenant(db: Session, wa_id: str) -> tuple[Tenant | None, ChannelConfig | None]:
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


async def _send_message(phone_number_id: str, access_token: str, wa_id: str, text: str) -> dict:
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


def _maybe_crm_bridge(db: Session, tenant_id, wa_id: str, text: str, contact_name: str | None) -> None:
    from ..integrations.credentials import get_credentials
    try:
        config = get_credentials(tenant_id, "zoho", db)
        from ..integrations.crm import get_crm_adapter
        adapter = get_crm_adapter("zoho", config)
        patient = adapter.find_patient(phone=wa_id)
        if not patient:
            parts = (contact_name or "WhatsApp User").split(None, 1)
            adapter.create_patient({
                "first_name": parts[0],
                "last_name": parts[1] if len(parts) > 1 else "User",
                "phone": wa_id,
            })
    except Exception:
        pass


@router.get("/webhook")
def verify_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    mode = request.query_params.get("hub.mode", "")
    token = request.query_params.get("hub.verify_token", "")
    challenge = request.query_params.get("hub.challenge", "")

    configs = (
        db.query(ChannelConfig)
        .filter(
            ChannelConfig.channel_type == "whatsapp",
            ChannelConfig.status == "active",
        )
        .all()
    )
    for cfg in configs:
        vt = cfg.config.get("verify_token", "")
        if mode == "subscribe" and token == vt:
            return int(challenge)

    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook")
async def handle_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
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

                tenant, cfg = _resolve_tenant(db, wa_id)
                if not tenant or not cfg:
                    continue

                phone_number_id = cfg.config.get("phone_number_id", "")
                access_token = cfg.config.get("access_token", "")

                if not check_rate_limit("whatsapp", wa_id):
                    await _send_message(phone_number_id, access_token, wa_id,
                        "Too many messages. Please slow down.")
                    continue

                flagged, category = moderate(text)
                if flagged:
                    await _send_message(phone_number_id, access_token, wa_id,
                        "Your message couldn't be processed due to content policy.")
                    continue

                up = text.strip().upper()
                if up in ("YES", "OPT-IN", "START", "CONSENT"):
                    ConsentManager.capture(
                        db=db,
                        patient_id=None,
                        consent_type="phi_whatsapp",
                        channel="whatsapp",
                        consent_text=f"Opt-in via WhatsApp: {text[:100]}",
                        tenant_id=tenant.id,
                        ip_address="whatsapp",
                    )
                    await _send_message(phone_number_id, access_token, wa_id,
                        "Thank you! You're now opted in to receive messages.")
                    continue

                if up in ("STOP", "UNSUBSCRIBE", "CANCEL", "OPT-OUT"):
                    db.flush()
                    await _send_message(phone_number_id, access_token, wa_id,
                        "You've been unsubscribed. Reply YES to opt back in.")
                    continue

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

                contacts = value.get("contacts") or []
                contact_name = contacts[0].get("profile", {}).get("name") if contacts else None

                conv = get_or_create_conversation(
                    db, tenant.id, wa_id,
                    channel="whatsapp",
                    user_display_name=contact_name or wa_id,
                )
                add_message(db, conv, "incoming", text, sender_type="customer")
                db.commit()

                from ..core.memory import get_conversation_history
                history = get_conversation_history(
                    tenant_id=str(tenant.id),
                    customer_id=wa_id,
                    db=db,
                )

                intent = await classify_intent(text, str(tenant.id), history=history)

                followup_intents = {
                    "followup_feeling_good", "followup_feeling_bad",
                    "followup_medication_ok", "followup_medication_not",
                }
                campaign_intents = {
                    "campaign_positive", "campaign_negative", "campaign_question",
                }
                if intent in followup_intents or intent in campaign_intents:
                    from ..core.events.schemas import CanonicalEvent
                    from ..core.workflows.registry import route_event

                    event_source = "followup" if intent in followup_intents else "marketing"
                    event = CanonicalEvent(
                        tenant_id=str(tenant.id),
                        event_type="patient_responded",
                        event_source=event_source,
                        entity_type="patient",
                        entity_id=wa_id,
                        payload={
                            "patient_id": wa_id,
                            "message": text,
                            "intent": intent,
                            "channel": "whatsapp",
                            "phone_number_id": phone_number_id,
                            "access_token": access_token,
                            "wa_id": wa_id,
                            "contact_name": contact_name,
                            "history": history,
                        },
                    )
                    await route_event(event, db)
                    continue

                if intent in ("appointment", "reschedule", "cancel", "availability", "emergency"):
                    from ..core.events.schemas import CanonicalEvent
                    from ..core.workflows.registry import route_event

                    if intent == "emergency":
                        await _send_message(phone_number_id, access_token, wa_id,
                            "If this is a medical emergency, please call 911 or your local emergency services immediately.")
                    else:
                        await _send_message(phone_number_id, access_token, wa_id,
                            "Let me help you with that. I'll check available options.")

                    event = CanonicalEvent(
                        tenant_id=str(tenant.id),
                        event_type="patient_message_received",
                        event_source="appointment",
                        entity_type="patient",
                        entity_id=wa_id,
                        payload={
                            "patient_id": wa_id,
                            "message": text,
                            "contact_name": contact_name,
                            "channel": "whatsapp",
                            "phone_number_id": phone_number_id,
                            "access_token": access_token,
                            "history": history,
                        },
                    )
                    await route_event(event, db)
                else:
                    result = await simple_llm_response(
                        tenant.id, text,
                        conversation_history=history,
                    )

                    response_text = result["response"]

                    log.response = response_text
                    log.resolution = "escalated" if result.get("escalated") else "resolved"
                    log.action_called = result.get("action_called", "")
                    log.latency_ms = result["latency_ms"]

                    tenant.dialogs_used += 1
                    if not result.get("escalated"):
                        tenant.resolved_count += 1

                    add_message(db, conv, "outgoing", response_text, sender_type="bot")
                    db.commit()

                    if response_text:
                        await _send_message(phone_number_id, access_token, wa_id, response_text)

                _maybe_crm_bridge(db, tenant.id, wa_id, text, contact_name)

    return {"ok": True}


def validate_config(config: dict) -> tuple[bool, str]:
    phone_number_id = config.get("phone_number_id", "")
    access_token = config.get("access_token", "")
    if not phone_number_id or not access_token:
        return False, "Missing phone_number_id or access_token"
    return True, "Config looks valid"
