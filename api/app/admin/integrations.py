from __future__ import annotations

import json

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from ..crypto import decrypt
from ..db import get_db
from ..models import NativeConnector, Tenant
from .deps import _ctx, get_admin_tenant
from .router import router

PROVIDER_WEBHOOK_EVENTS = {
    "shopify": ["orders/create", "orders/updated", "fulfillments/create", "fulfillments/update", "customers/create", "customers/update"],
}

PROVIDER_REQUIRED_FIELDS = {
    "shopify": ["shop_domain", "access_token"],
}


@router.get("/api/integrations")
def api_integrations(
    request: Request,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    ctx = _ctx(request)
    base = ctx.get("public_base_url", "").rstrip("/")
    webhook_base = f"{base}/integrations/webhooks" if base else None

    connectors = db.query(NativeConnector).filter(NativeConnector.tenant_id == tenant.id).all()
    conn_map = {c.provider: c for c in connectors}

    result = []
    for provider in ("shopify",):
        c = conn_map.get(provider)
        status = "disconnected"
        if c and c.status == "connected":
            try:
                creds = json.loads(decrypt(c.credentials))
                required = PROVIDER_REQUIRED_FIELDS.get(provider, [])
                status = "connected" if all(creds.get(f) for f in required) else "disconnected"
            except Exception:
                status = "disconnected"

        result.append({
            "provider": provider,
            "status": status,
            "has_webhook_secret": bool((c.meta or {}).get("webhook_secret")) if c else False,
            "webhook_url": f"{webhook_base}/{provider}" if webhook_base else None,
            "webhook_events": PROVIDER_WEBHOOK_EVENTS.get(provider, []),
            "created_at": c.created_at.isoformat() if c and c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c and c.updated_at else None,
        })

    return {
        "native_connectors": result,
        "webhook_base_url": webhook_base,
    }
