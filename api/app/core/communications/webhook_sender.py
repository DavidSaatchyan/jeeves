from __future__ import annotations

import hashlib
import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import WebhookConfig

logger = logging.getLogger(__name__)


async def fire_outgoing_webhooks(db: Session, tenant_id, user_id: str, event: str, result: dict):
    """Send outgoing webhooks directly (no Celery) for configured events."""
    import httpx

    cfg = db.execute(select(WebhookConfig).where(
        WebhookConfig.tenant_id == tenant_id,
        WebhookConfig.enabled == True,  # noqa: E712
    )).scalar_one_or_none()
    if not cfg or not cfg.events:
        return

    events = cfg.events if isinstance(cfg.events, list) else []
    if event not in events:
        return

    payload = {
        "tenant_id": str(tenant_id),
        "user_id": user_id,
        "event": event,
        "response": result.get("response", ""),
        "action_called": result.get("action_called"),
        "escalated": result.get("escalated", False),
        "session_id": result.get("session_id"),
    }

    if not cfg.outgoing_url:
        return

    body = json.dumps(payload, ensure_ascii=False)
    headers = {"Content-Type": "application/json"}
    if cfg.outgoing_secret:
        try:
            secret = cfg.outgoing_secret
            headers["X-Jeeves-Signature"] = hashlib.sha256((secret + body).encode()).hexdigest()
        except Exception:
            pass

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.post(cfg.outgoing_url, content=body, headers=headers)
    except Exception as e:
        logger.warning("outgoing webhook failed: %s", e)
