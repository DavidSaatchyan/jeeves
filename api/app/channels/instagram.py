from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ChannelConfig, Tenant
from ..agents.service import process_message
from ..channels.registry import channel_cache

_IG_GRAPH_API = "https://graph.facebook.com/v22.0"
logger = logging.getLogger("jeeves.instagram")

router = APIRouter(prefix="/channels/instagram", tags=["instagram"])


def _resolve_tenant(db: Session, ig_user_id: str) -> tuple[Tenant | None, ChannelConfig | None]:
    entry = channel_cache.resolve_instagram(ig_user_id)
    if entry:
        tenant_id, config_id = entry
        return db.get(Tenant, tenant_id), db.get(ChannelConfig, config_id)
    configs = (
        db.execute(select(ChannelConfig).where(
            ChannelConfig.channel_type == "instagram",
            ChannelConfig.status == "active",
        )).scalars().all()
    )
    for cfg in configs:
        if cfg.config.get("instagram_account_id"):
            return db.get(Tenant, cfg.tenant_id), cfg
    return None, None


async def _send_message(access_token: str, ig_account_id: str, recipient_id: str, text: str) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            f"{_IG_GRAPH_API}/{ig_account_id}/messages",
            params={"access_token": access_token},
            json={
                "recipient": {"id": recipient_id},
                "message": {"text": text},
            },
        )
        r.raise_for_status()
        return r.json()


@router.get("/webhook")
def verify_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    mode = request.query_params.get("hub.mode", "")
    token = request.query_params.get("hub.verify_token", "")
    challenge = request.query_params.get("hub.challenge", "")

    configs = (
        db.execute(select(ChannelConfig).where(
            ChannelConfig.channel_type == "instagram",
            ChannelConfig.status == "active",
        )).scalars().all()
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
        messaging = entry.get("messaging") or []
        for msg in messaging:
            message = msg.get("message") or {}
            if message.get("is_echo"):
                continue
            sender_id = msg.get("sender", {}).get("id", "")
            text = message.get("text", "")
            if not sender_id or not text:
                continue

            tenant, cfg = _resolve_tenant(db, sender_id)
            if not tenant or not cfg:
                continue

            access_token = cfg.config.get("access_token", "")
            ig_account_id = cfg.config.get("instagram_account_id", "")

            result = await process_message(
                tenant_id=str(tenant.id),
                customer_id=sender_id,
                message=text,
                channel="instagram",
                db=db,
            )

            if result.blocked:
                await _send_message(access_token, ig_account_id, sender_id,
                    "Your message couldn't be processed due to content policy.")
                continue
            if result.rate_limited:
                await _send_message(access_token, ig_account_id, sender_id,
                    "Too many messages. Please slow down.")
                continue
            if result.response:
                await _send_message(access_token, ig_account_id, sender_id, result.response)

    return {"status": "ok"}
