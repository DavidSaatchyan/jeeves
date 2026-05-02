"""Webhook support: incoming context fetching and outgoing event notifications.

Task 9: Incoming webhooks enrich agent context at conversation start.
Outgoing webhooks fire on configured events with HMAC-SHA256 signatures.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any
from uuid import UUID

import httpx
from jsonpath_ng.ext import parse as jp_parse
from sqlalchemy.orm import Session

from .crypto import decrypt
from .models import WebhookConfig


def _hmac_sha256(secret: str, payload: str) -> str:
    """Compute HMAC-SHA256 hex digest."""
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _apply_field_mapping(data: Any, mapping: dict[str, str]) -> dict[str, Any]:
    """Map response fields using JSONPath expressions."""
    out = {}
    for field, expr in (mapping or {}).items():
        try:
            matches = [m.value for m in jp_parse(expr).find(data)]
            out[field] = matches[0] if matches else None
        except Exception:
            out[field] = None
    return out


async def fetch_incoming_webhook_context(
    db: Session,
    tenant_id: UUID,
    user_id: str,
    extra_fields: dict | None = None,
) -> dict:
    """POST to configured incoming_url with HMAC-signed payload.

    Returns merged context dict (field_mapping applied).
    On failure (timeout, non-2xx): logs and returns empty dict — never blocks.
    """
    cfg = (
        db.query(WebhookConfig)
        .filter(
            WebhookConfig.tenant_id == tenant_id,
            WebhookConfig.enabled == True,  # noqa: E712
        )
        .first()
    )
    if not cfg or not cfg.incoming_url:
        return {}

    secret_plain = ""
    if cfg.incoming_secret:
        try:
            secret_plain = decrypt(cfg.incoming_secret)
        except Exception:
            secret_plain = ""

    payload = {
        "tenant_id": str(tenant_id),
        "user_id": user_id,
        "extra_fields": extra_fields or {},
    }
    body = json.dumps(payload, ensure_ascii=False)
    signature = _hmac_sha256(secret_plain, body) if secret_plain else ""

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if signature:
        headers["X-Jeeves-Signature"] = f"sha256={signature}"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(cfg.incoming_url, content=body, headers=headers)
        if r.status_code >= 400:
            print(f"[webhook] incoming returned {r.status_code}", flush=True)
            return {}
        data = r.json()
    except httpx.TimeoutException:
        print("[webhook] incoming webhook timed out", flush=True)
        return {}
    except Exception as e:
        print(f"[webhook] incoming webhook error: {e}", flush=True)
        return {}

    return _apply_field_mapping(data, cfg.field_mapping or {})


def compute_outgoing_signature(secret: str, payload: str) -> str:
    """Compute HMAC-SHA256 signature for outgoing webhook."""
    return f"sha256={_hmac_sha256(secret, payload)}"
