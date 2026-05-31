from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

WHATSAPP_API = "https://graph.facebook.com/v17.0/{phone_number_id}/messages"


async def send_whatsapp_message(phone_number_id: str, access_token: str, wa_id: str, text: str) -> dict:
    """Send a WhatsApp text message via Cloud API.

    This is the shared delivery function used by workflows and channels.
    """
    url = WHATSAPP_API.format(phone_number_id=phone_number_id)
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            url,
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


async def send_email(to: str, subject: str, body: str) -> bool:
    """Email delivery is being removed (Phase 1). WhatsApp replaces email.
    This stub remains to avoid breaking existing communication service imports."""
    logger.warning("email delivery removed: would send to %s subject=%s", to, subject)
    return False
