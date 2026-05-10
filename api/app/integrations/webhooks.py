"""Webhook receivers for Stripe, Shopify, and Recharge.
Converts external webhook payloads → CanonicalEvents → dispatched to workflows.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..core.events.dispatcher import dispatch_event
from ..core.events.schemas import CanonicalEvent
from ..db import get_db
from ..models import NativeConnector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/webhooks", tags=["integrations", "webhooks"])


# ---------------------------------------------------------------------------
# Stripe
# ---------------------------------------------------------------------------

@router.post("/stripe", status_code=200)
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if not raw_body or not sig_header:
        raise HTTPException(status_code=400, detail="Missing body or stripe-signature header")

    # Iterate all connected Stripe connectors to find the matching tenant
    connectors = db.query(NativeConnector).filter(
        NativeConnector.provider == "stripe",
        NativeConnector.status == "connected",
    ).all()

    if not connectors:
        logger.warning("no connected stripe connectors found")
        raise HTTPException(status_code=404, detail="No Stripe connector configured")

    import stripe as stripe_lib

    matched_tenant_id: str | None = None
    parsed_event: dict[str, Any] | None = None

    for cxn in connectors:
        secret = (cxn.meta or {}).get("webhook_secret", "")
        if not secret:
            continue
        try:
            stripe_lib.Webhook.construct_event(payload=raw_body, sig_header=sig_header, webhook_secret=secret)
            matched_tenant_id = str(cxn.tenant_id)
            parsed_event = json.loads(raw_body)
            break
        except stripe_lib.error.SignatureVerificationError:
            continue
        except Exception:
            logger.exception("stripe webhook parsing error for connector %s", cxn.id)
            continue

    if not matched_tenant_id or not parsed_event:
        raise HTTPException(status_code=401, detail="Invalid stripe signature")

    from .stripe.events import normalize_webhook

    canonical = normalize_webhook(parsed_event, matched_tenant_id)
    if not canonical:
        return {"ok": True, "skipped": True, "reason": "unmapped_event_type"}

    await _dispatch(canonical, db)
    return {"ok": True, "event_id": canonical.event_id}


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
    if webhook_secret and not _verify_hmac(raw_body, hmac_header, webhook_secret):
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
# Recharge
# ---------------------------------------------------------------------------

@router.post("/recharge", status_code=200)
async def recharge_webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    shop_domain = request.headers.get("X-Recharge-Shop-Domain", "")
    hmac_header = request.headers.get("X-Recharge-Hmac-SHA256", "")

    if not raw_body:
        raise HTTPException(status_code=400, detail="Missing body")

    # Recharge sometimes omits the shop domain header; fall back to trying all connectors
    connector: NativeConnector | None = None
    if shop_domain:
        connector = _find_connector_by_shop_domain(db, "recharge", shop_domain)

    if not connector:
        connector = _find_recharge_connector_by_hmac(db, raw_body, hmac_header)

    if not connector:
        raise HTTPException(status_code=404, detail="No Recharge connector found")

    webhook_secret = (connector.meta or {}).get("webhook_secret", "")
    if webhook_secret and not _verify_hmac(raw_body, hmac_header, webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid HMAC signature")

    payload = json.loads(raw_body) if raw_body else {}

    from .recharge.events import normalize_webhook

    canonical = normalize_webhook(payload, str(connector.tenant_id))
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


def _find_recharge_connector_by_hmac(db: Session, raw_body: bytes, hmac_header: str) -> NativeConnector | None:
    """If no shop domain is available, try each Recharge connector's webhook secret."""
    connectors = db.query(NativeConnector).filter(
        NativeConnector.provider == "recharge",
        NativeConnector.status == "connected",
    ).all()

    for cxn in connectors:
        secret = (cxn.meta or {}).get("webhook_secret", "")
        if not secret:
            continue
        if _verify_hmac(raw_body, hmac_header, secret):
            return cxn

    return None


def _verify_hmac(raw_body: bytes, header_value: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature (Shopify & Recharge style)."""
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", header_value) or hmac.compare_digest(
        expected, header_value
    )


async def _dispatch(event: CanonicalEvent, db: Session) -> None:
    """Dispatch a CanonicalEvent through the workflow engine."""
    try:
        await dispatch_event(event, db)
    except Exception:
        logger.exception("failed to dispatch event %s", event.event_id)
