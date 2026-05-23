"""Webhook receivers for Shopify.
Converts external webhook payloads → CanonicalEvents → dispatched to workflows.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..core.events.dispatcher import dispatch_event
from ..core.events.schemas import CanonicalEvent
from ..db import get_db
from ..models import NativeConnector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/webhooks", tags=["integrations", "webhooks"])


# ---------------------------------------------------------------------------
# Shopify
# ---------------------------------------------------------------------------

@router.post("/shopify", status_code=200)
async def shopify_webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    shop_domain = request.headers.get("X-Shopify-Shop-Domain", "")
    hmac_header = request.headers.get("X-Shopify-Hmac-SHA256", "")

    if not raw_body or not shop_domain or not hmac_header:
        raise HTTPException(status_code=400, detail="Missing body, X-Shopify-Shop-Domain, or X-Shopify-Hmac-SHA256")

    connector = _find_connector_by_shop_domain(db, "shopify", shop_domain)
    if not connector:
        raise HTTPException(status_code=404, detail="No Shopify connector found for this shop domain")

    webhook_secret = (connector.meta or {}).get("webhook_secret", "")
    if webhook_secret and not _verify_shopify_hmac(raw_body, hmac_header, webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid HMAC signature")

    topic = request.headers.get("X-Shopify-Topic", "")
    payload = json.loads(raw_body) if raw_body else {}

    from .shopify.events import normalize_webhook

    canonical = normalize_webhook({"topic": topic, "data": payload}, str(connector.tenant_id))
    if not canonical:
        return {"ok": True, "skipped": True, "reason": "unmapped_event_type"}

    await _dispatch(canonical, db)
    return {"ok": True, "event_id": canonical.event_id}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_connector_by_shop_domain(db: Session, provider: str, shop_domain: str) -> NativeConnector | None:
    """Decrypt credentials of each connected connector and match shop_domain."""
    from ..crypto import decrypt

    connectors = db.query(NativeConnector).filter(
        NativeConnector.provider == provider,
        NativeConnector.status == "connected",
    ).all()

    for cxn in connectors:
        try:
            creds = json.loads(decrypt(cxn.credentials))
            stored_domain = creds.get("shop_domain", "")
            if stored_domain and stored_domain.lower() == shop_domain.lower():
                return cxn
        except Exception:
            logger.warning("failed to decrypt/parse credentials for connector %s", cxn.id, exc_info=True)
            continue

    return None


def _verify_shopify_hmac(raw_body: bytes, header_value: str, secret: str) -> bool:
    """Shopify HMAC verification: HMAC-SHA256(secret, raw_body) → base64 digest."""
    expected = base64.b64encode(
        hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    ).decode()
    return hmac.compare_digest(expected, header_value)


async def _dispatch(event: CanonicalEvent, db: Session) -> None:
    """Dispatch a CanonicalEvent through the workflow engine."""
    try:
        await dispatch_event(event, db)
    except Exception:
        logger.exception("failed to dispatch event %s", event.event_id)
