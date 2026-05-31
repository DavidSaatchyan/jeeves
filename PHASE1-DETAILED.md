# Phase 1: Foundation — Detailed Work Plan

> **Duration:** Days 1-3
> **Goal:** Remove all Shopify/e-commerce dead code while keeping app functional.
> **Verification Gate:** `python -c "from app.main import app"` passes AND admin panel loads without 500 errors.

---

## Summary of Changes

| Step | File(s) | Action | Risk |
|------|---------|--------|------|
| 1.1 | `integrations/shopify/` | DELETE entire directory | High — WISMO depends on it |
| 1.2 | `integrations_routes.py` | DELETE entire file | Medium — only Shopify test |
| 1.3 | `integrations/credentials.py` | EDIT — remove `frozenset({"shopify"})` | Low |
| 1.4 | `integrations/email/` | DELETE entire directory | Low — email channel removed |
| 1.5 | `channels/base.py` | DELETE file | Low — not referenced |
| 1.6 | `channels/rest.py` | DELETE file | Low — not referenced |
| 1.7 | `core/commerce/` | DELETE entire directory | Low — not referenced |
| 1.8 | `models.py` | EDIT — strip e-commerce fields | Medium — FK dependencies |
| 1.9 | `config.py` | EDIT — remove Shopify env vars | Low |
| 1.10 | `main.py` | EDIT — remove dead imports | Medium |
| 1.11 | `admin/integrations.py` | EDIT — remove Shopify entries | Medium — admin panel uses this |
| 1.12 | `admin/agents.py` | EDIT — remove WISMO specific code | Medium — admin panel uses this |
| 1.13 | `admin/logs.py` | CHECK — uses `billing.usage()` | Low — keep `billing.py` |
| 1.14 | `admin/policies.py` | EDIT — remove `wismo` references | Low |
| 1.15 | `channels/widget.py` | EDIT — remove email channel refs | Low |
| 1.16 | `templates/` | EDIT — remove email/Shopify/WISMO refs | Low |
| 1.17 | `core/workflows/wismo.py` | DELETE | High — needs import cleanup |
| 1.18 | `core/workflows/wismo_service.py` | DELETE | High — needs import cleanup |
| 1.19 | `core/workflows/__init__.py` | EDIT — remove WISMO init | Medium |
| 1.20 | `core/events/schemas.py` | EDIT — remove Shopify event types | Low |
| 1.21 | `integrations/webhooks.py` | DELETE | Medium — Shopify webhooks |
| 1.22 | `shared/inbox_writer.py` | EDIT — remove `shopify_customer_id` ref | Low |
| 1.23 | Alembic migration | ADD — migration to drop e-commerce tables | High — data loss risk |
| 1.24 | Verification | `python -c "from app.main import app"` | Critical |

---

## Step 1.1 — Delete `integrations/shopify/`

**Files to delete:**
- `integrations/shopify/__init__.py`
- `integrations/shopify/client.py`
- `integrations/shopify/actions.py`
- `integrations/shopify/events.py`
- `integrations/shopify/__pycache__/` (all files)

**Impact analysis:**
- `core/workflows/wismo_service.py` imports from `integrations.shopify.actions` → **DELETE wismo_service too** (Step 1.17)
- `integrations/webhooks.py` imports from `integrations.shopify.events` → **DELETE or EDIT webhooks.py** (Step 1.21)
- `integrations/shopify/__init__.py` exports `normalize_webhook`, `fetch_customer`, etc. → only used by code being deleted

**Command:**
```powershell
Remove-Item -Recurse -Force api/app/integrations/shopify/
```

---

## Step 1.2 — Delete `integrations_routes.py`

**Entire file `integrations_routes.py`** — only contains Shopify test logic.

**Impact analysis:**
- Imported by `main.py: from . import admin, auth, integrations_routes, ...`
- Routers: prefix `/integrations` — includes list/create/delete/test connectors
- **BUT** `admin/integrations.py` ALSO has `/admin/api/integrations` which is what the frontend calls
- The frontend (`connections.html`) calls:
  - `GET /admin/api/integrations` → handled by `admin/integrations.py`
  - `POST /integrations/native` → handled by `integrations_routes.py` ← **this will break**
  - `POST /integrations/native/{provider}/test` → handled by `integrations_routes.py` ← **will break**
  - `DELETE /integrations/native/{provider}` → handled by `integrations_routes.py` ← **will break**

**Action:** DELETE the file; move the generic CRUD logic to `admin/integrations.py` so the frontend still works for CRM connectors later.

**Create replacement in `admin/integrations.py`:**

Add these parts at the end of `admin/integrations.py`:

```python
# ── Generic Native Connector CRUD (moved from integrations_routes.py) ──

@router.post("/api/integrations/native", status_code=201)
def admin_connect_native(...):
    # same logic as integrations_routes.connect_native
    # but without Shopify-specific provider check
    ...

@router.delete("/api/integrations/native/{provider}")
def admin_disconnect_native(...):
    ...

@router.post("/api/integrations/native/{provider}/test")
def admin_test_native(...):
    # remove the Shopify-specific test
    ...
```

Details in Step 1.11 below.

---

## Step 1.3 — Edit `integrations/credentials.py`

**Change `_PROVIDERS` set:**

```python
# BEFORE:
_PROVIDERS = frozenset({"shopify"})

# AFTER:
_PROVIDERS: frozenset[str] = frozenset()
```

This makes `get_credentials` still functional (it only checks membership) but allows CRM providers to be added in Phase 3.

---

## Step 1.4 — Delete `integrations/email/`

**Files to delete:**
- `integrations/email/__init__.py`
- `integrations/email/provider.py`
- `integrations/email/__pycache__/`

**Impact analysis:**
- `core/communications/delivery.py` has `from ...integrations.email.provider import SendGridProvider` (inside a local import) — **will break**
- `integrations/email/__init__.py` exports `SendGridProvider, ResendProvider`

**Action:**
1. Delete `integrations/email/`
2. In `core/communications/delivery.py`, remove the local imports of `SendGridProvider` and `ResendProvider`
3. The `_get_email_provider()` function in `delivery.py` will need to be stubbed or removed (since email channel is going away)

**Command:**
```powershell
Remove-Item -Recurse -Force api/app/integrations/email/
```

---

## Step 1.5 — Delete `channels/base.py`

No impact — `channels/rest.py` imports from it, but both are being deleted.

---

## Step 1.6 — Delete `channels/rest.py`

No impact — not imported anywhere.

---

## Step 1.7 — Delete `core/commerce/`

**Files to delete:**
- `core/commerce/__init__.py`
- `core/commerce/billing.py` (has `InvoiceService`, `PaymentFailureService`)
- `core/commerce/customer.py` (has `CustomerService`)
- `core/commerce/subscription.py` (has `SubscriptionService`)

**Impact analysis:**
- Zero imports found via grep: `from.*core\.commerce` → no results
- These classes (`InvoiceService`, `PaymentFailureService`, `CustomerService`, `SubscriptionService`) are NOT referenced anywhere

Safe to delete.

---

## Step 1.8 — Edit `models.py` — Strip E-commerce Fields

### Fields to remove from `Customer` model:
| Field | Line | Reason |
|-------|------|--------|
| `shopify_customer_id` | 330 | Shopify-specific |
| `stripe_customer_id` | 331 | Not used, e-commerce |
| `recharge_customer_id` | 332 | Not used, e-commerce |
| `risk_level` | 349 | WISMO-specific |
| `sentiment_state` | 350 | WISMO-specific |
| `sentiment_trend` | 351 | WISMO-specific |
| `frustration_score` | 352 | WISMO-specific |

### Models to delete entirely:
| Model | Lines | Reason |
|-------|-------|--------|
| `ProductCatalog` | 66-86 | Product catalog — e-commerce |
| `CatalogVariant` | 88-101 | Product variants — e-commerce |
| `Compatibility` | 103-117 | Product compatibility — e-commerce |
| `Subscription` | 358-376 | E-commerce subscriptions |
| `Invoice` | 379-397 | E-commerce invoices |
| `PaymentFailure` | 399-416 | E-commerce payment failures |
| `PolicySet` | 538-551 | Policy engine — rebuild later for medical |
| `Escalation` | 489-507 | Too coupled to WISMO — rebuild later |
| `NotificationPreferences` | 568-579 | Old notification system |

### Models to keep (with potential field changes):
| Model | Action |
|-------|--------|
| `Tenant` | Keep — remove `dialogs_used`, `resolved_count` |
| `FileRecord` | Keep as-is |
| `ChatLog` | Keep as-is |
| `ConversationRating` | Keep as-is |
| `WebhookConfig` | Keep — repurpose for CRM webhooks |
| `ChannelConfig` | Keep as-is |
| `ApiKey` | Keep as-is |
| `Conversation` | Keep — remove `workflow_id`, `escalation_id`, `workflow_type` |
| `Message` | Keep — remove `workflow_id`, `workflow_state` |
| `OperatorNote` | Keep as-is |
| `CannedResponse` | Keep as-is |
| `Workflow` | Keep — repurpose for medical workflows |
| `WorkflowTransition` | Keep |
| `Communication` | Keep |
| `CanonicalEvent` | Keep |
| `TimelineEvent` | Keep |
| `AIInteraction` | Keep |
| `NativeConnector` | Keep — repurpose for CRM connectors |

### After deletion, add new medical models as stubs:

```python
class Patient(Base):
    """Placeholder for Phase 2 — medical patient model."""
    __tablename__ = "patients"
    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    external_id = Column(Text)         # CRM patient ID
    first_name = Column(Text, nullable=False)
    last_name = Column(Text, nullable=False)
    email = Column(Text)
    phone = Column(Text, nullable=False)
    date_of_birth = Column(DateTime)
    consent_status = Column(String(16), default="pending")
    metadata = Column(JSONB, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
```

Add only models that are stubs — full medical model set comes in Phase 2.

---

## Step 1.9 — Edit `config.py`

**Remove these fields from `Settings`:**
```python
# BEFORE:
shopify_shop: str = ""
shopify_access_token: str = ""
sendgrid_api_key: str = ""
resend_api_key: str = ""
hubspot_client_id: str = ""       # Keep — needed in Phase 3
hubspot_client_secret: str = ""   # Keep — needed in Phase 3
hubspot_redirect_uri: str = ""    # Keep — needed in Phase 3

# AFTER:
# Remove: shopify_shop, shopify_access_token, sendgrid_api_key, resend_api_key
# Keep: hubspot_client_id, hubspot_client_secret, hubspot_redirect_uri
```

**Remove `_REQUIRED_SECRETS` entry if needed** — Shopify env vars were not in `_REQUIRED_SECRETS` so no change needed.

---

## Step 1.10 — Edit `main.py`

**Remove imports:**
```python
# BEFORE:
from . import admin, auth, integrations_routes, knowledge, routes_chat
from .integrations import webhooks as webhooks_router

# AFTER:
from . import admin, auth, knowledge, routes_chat
```

**Remove router includes:**
```python
# BEFORE:
app.include_router(integrations_routes.router)
app.include_router(webhooks_router.router)

# AFTER:
# Remove both lines
```

**Update `init_workflows` in startup:** Change to not try to import WISMO:

```python
@app.on_event("startup")
def on_startup() -> None:
    _run_alembic_migrations()
    from .channels.registry import build_channel_cache
    from .db import SessionLocal
    db = SessionLocal()
    try:
        build_channel_cache(db)
        # init_workflows() removed — WISMO is gone, medical workflows TBD
    finally:
        db.close()
```

---

## Step 1.11 — Edit `admin/integrations.py`

**Current content analysis:**
This file has:
- `_WEBHOOK_EVENTS` dict with Shopify events → REMOVE
- `_CONNECTOR_FIELDS` dict with Shopify fields → REMOVE (or leave empty for future)
- `api_integrations` GET handler → KEEP (generic)
- Provider iteration `for provider in ("shopify",)` → REMOVE

**Specific changes:**

1. Remove `_WEBHOOK_EVENTS` dict entirely (Shopify-specific)
2. Replace `_CONNECTOR_FIELDS` with an empty dict or generic placeholder
3. Change the provider iteration to return an empty list
4. **Add** the native connector CRUD that was in `integrations_routes.py` (POST/DELETE/test)

**New code shape:**
```python
from __future__ import annotations

import json
import logging
from datetime import datetime

import httpx
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.deps import get_current_tenant
from ..crypto import ConnectorError, decrypt, encrypt
from ..db import get_db
from ..models import NativeConnector, Tenant
from ..config import get_settings
from .deps import get_admin_tenant
from .router import router

logger = logging.getLogger(__name__)

# CRM providers will be registered here in Phase 3
_CONNECTOR_FIELDS: dict[str, list[str]] = {}
_WEBHOOK_EVENTS: dict[str, list[str]] = {}


def _mask_creds(creds: str) -> dict:
    try:
        data = json.loads(creds)
        masked = {}
        for k, v in data.items():
            if any(s in k.lower() for s in ("secret", "token", "key", "password")):
                masked[k] = v[:6] + "••••" if len(v) > 6 else "••••"
            else:
                masked[k] = v
        return masked
    except (json.JSONDecodeError, TypeError):
        return {"masked": True}


@router.get("/api/integrations")
def api_integrations(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    connectors = db.query(NativeConnector).filter(NativeConnector.tenant_id == tenant.id).all()
    return {
        "native_connectors": [
            {
                "id": str(c.id),
                "provider": c.provider,
                "status": c.status,
                "config_mask": _mask_creds(c.credentials) if c.status == "connected" else {},
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                "connector_fields": _CONNECTOR_FIELDS.get(c.provider, []),
            }
            for c in connectors
        ],
        "providers": list(_CONNECTOR_FIELDS.keys()),
    }


@router.post("/api/integrations/native", status_code=201)
def admin_connect_native(
    body: dict,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    provider = body.get("provider", "").lower()
    credentials = body.get("credentials", {})
    if not credentials:
        raise HTTPException(status_code=400, detail="Credentials required")

    existing = db.query(NativeConnector).filter(
        NativeConnector.tenant_id == tenant.id,
        NativeConnector.provider == provider,
    ).first()

    encrypted = encrypt(json.dumps(credentials))
    webhook_secret = body.get("webhook_secret", "")

    if existing:
        existing.credentials = encrypted
        existing.status = "connected"
        existing.updated_at = datetime.utcnow()
        meta = dict(existing.meta or {})
        if webhook_secret:
            meta["webhook_secret"] = webhook_secret
        existing.meta = meta
    else:
        meta = {}
        if webhook_secret:
            meta["webhook_secret"] = webhook_secret
        existing = NativeConnector(
            tenant_id=tenant.id,
            provider=provider,
            status="connected",
            credentials=encrypted,
            meta=meta,
        )
        db.add(existing)

    db.commit()
    return {"ok": True, "provider": provider, "status": "connected"}


@router.delete("/api/integrations/native/{provider}")
def admin_disconnect_native(
    provider: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    provider = provider.lower()
    connector = db.query(NativeConnector).filter(
        NativeConnector.tenant_id == tenant.id,
        NativeConnector.provider == provider,
    ).first()
    if not connector:
        raise HTTPException(status_code=404, detail=f"Connector '{provider}' not found")
    db.delete(connector)
    db.commit()
    return {"ok": True, "provider": provider, "status": "disconnected"}


@router.post("/api/integrations/native/{provider}/test")
def admin_test_native(
    provider: str,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    provider = provider.lower()
    from ..integrations.credentials import get_credentials
    try:
        creds = get_credentials(tenant.id, provider, db)
    except ConnectorError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # Provider-specific test will be added in Phase 3
    return {"ok": True, "provider": provider, "message": "Connection stored (test TBD for this provider)"}
```

---

## Step 1.12 — Edit `admin/agents.py`

**Current WISMO-specific code:**
- `WISMO_FUNNEL = {...}` dict — REMOVE
- `FUNNEL_STAGES = WISMO_FUNNEL if agent_type == "wismo" else PAYGUARD_FUNNEL` — REMOVE PAYGUARD, keep infrastructure for future agents
- WISMO policy reading — REMOVE

The frontend `agents.html` expects:
- `GET /admin/api/policies` → return empty/placeholder policies
- `PUT /admin/api/policies/enabled_workflows` → accept any workflow list
- `PUT /admin/api/policies/wismo` → remove or keep as generic stub
- `GET /admin/api/workflows?limit=200` → return workflows (any type)
- `GET /admin/api/integrations` → already handled by integrations.py

**Specific changes:**

1. Remove `WISMO_FUNNEL` and `PAYGUARD_FUNNEL` constants
2. Replace `api_get_policies` — remove `wismo` policy key
3. Replace `api_get_workflows` — keep generic, remove WISMO-specific filtering
4. Replace `api_policies_update_wismo` → remove or make generic

---

## Step 1.13 — Verify `admin/logs.py`

This file imports `from .. import billing` which refers to the top-level `billing.py`. This file:
- `GET /admin/api/billing` → returns `billing.usage(tenant)`
- `GET /admin/api/logs` → returns ChatLog with cursor pagination
- `POST /admin/api/ratings` → submit rating
- `GET /admin/api/ratings` → list ratings

**Action:** KEEP `billing.py` as-is. It's not e-commerce — it's internal usage tracking. The `admin/logs.py` is still needed by the admin panel.

---

## Step 1.14 — Edit `admin/policies.py`

**Current WISMO references:**
```python
"wismo": ps.wismo_policy or {},  # Line 34
"wismo": "wismo_policy",         # Line 55
```

**Action:** Remove `wismo` entries. Keep only generic policy fields.

```python
# Line 34 — BEFORE:
"wismo": ps.wismo_policy or {},
"enabled_workflows": ps.enabled_workflows or [],

# Line 34 — AFTER:
"enabled_workflows": ps.enabled_workflows or [],
```

```python
# Line 55 — BEFORE:
"wismo": "wismo_policy",

# Line 55 — AFTER:
# (remove this line entirely)
```

Also update `PolicySet` model in `models.py` to remove `wismo_policy` field (already being deleted in Step 1.8).

---

## Step 1.15 — Edit `channels/widget.py`

**Remove email channel references:**
- The widget may reference `email` as a channel type — keep `web_widget` and `whatsapp` only
- Remove any email-specific rate limiting or delivery logic

**Specific grep needed:** Search for "email" in `channels/widget.py` and strip any email-related code paths.

---

## Step 1.16 — Edit Templates

### `agents.html`:
- Replace WISMO-specific text with generic "Agents" placeholder
- Remove WISMO funnel visualization (state distribution)
- Remove Shopify connection warning
- Keep the infrastructure (enable/disable toggle, stats cards) for future agents

### `channels.html`:
- Remove the Email tab entirely
- Rename "Website Widget" → "Widget"
- WhatsApp tab stays as "Coming soon" → will be implemented in Phase 4
- Remove email config (SMTP host, port, etc.)

### `connections.html`:
- Remove Shopify-specific fields (`sf-shop`, `sf-token`)
- Remove Shopify-specific webhook setup instructions
- Change "Connect Shopify" → "Connect CRM" placeholder
- Keep the generic connector UI framework

### `landing.html`:
- **Major rewrite deferred to Phase 7** — for now, just change obvious Shopify/e-commerce references
- Search for "Shopify", "e-commerce", "order", "WISMO" and replace with generic terms
- Add placeholder for medical value proposition

### `inbox.html` + `inbox.js`:
- Search for `subscriptions` API call: `GET /admin/api/customers/{id}/subscriptions`
- Either remove this call or stub the endpoint (remove from `admin/agents.py`)
- Remove the "Subscriptions" section from customer profile sidebar

---

## Step 1.17 — Delete `core/workflows/wismo.py`

**Entire file.** WISMO state machine is no longer needed.

**Impact analysis:**
- `core/workflows/__init__.py` imports from `.wismo` → edit in Step 1.19
- `core/workflows/registry.py` has `from .wismo import WISMO_INITIAL_STATE` (inside local import) → edit
- `core/workflows/wismo_service.py` imports from `.wismo` → delete wismo_service too (Step 1.18)

---

## Step 1.18 — Delete `core/workflows/wismo_service.py`

**Entire file.** Shopify service layer for WISMO.

**Impact:** Only imported by `core/workflows/wismo.py` (already deleted) and `core/workflows/registry.py` (edit in Step 1.19).

---

## Step 1.19 — Edit `core/workflows/__init__.py`

**Remove WISMO import:**

```python
# BEFORE:
from .registry import register_workflow

def init_workflows():
    from .wismo import WismoWorkflow
    ...

# AFTER:
# Remove the file entirely or leave empty with:
from .registry import register_workflow

def init_workflows():
    """Placeholder — medical workflows registered in Phase 5."""
    pass
```

---

## Step 1.20 — Edit `core/events/schemas.py`

**Remove Shopify event types:**
```python
# BEFORE:
# Shopify / WISMO
SHOPIFY_ORDER_CREATED = "shopify.order.created"
...

# AFTER: remove all Shopify-related constants
```

Keep only generic event types that may be reused (`PATIENT_MESSAGE_RECEIVED`, `APPOINTMENT_REQUESTED`, etc.).

---

## Step 1.21 — Delete/Edit `integrations/webhooks.py`

This file is the Shopify webhook receiver + HMAC verification.

**Option A:** DELETE the entire file and its router include (recommended for Phase 1 — CRM webhooks will be different).

**Impact:** Removes the `/integrations/shopify` webhook endpoint. CRM webhooks will have different signatures and endpoints.

**But** the webhook infrastructure (routing to event dispatcher) should be preserved in a generic form. Extract the generic dispatch logic and delete only the Shopify-specific parts.

Better approach:
1. Delete `integrations/webhooks.py`
2. Create a minimal `integrations/webhooks.py` later when CRM integration is built

---

## Step 1.22 — Edit `shared/inbox_writer.py`

**Remove `shopify_customer_id` reference:**

```python
# Line 22 — BEFORE:
Customer.shopify_customer_id == conversation.user_id,

# AFTER:
Customer.phone == conversation.user_id,
```

Since the `shopify_customer_id` field is being removed from `Customer` model in Step 1.8, this reference will cause an error. Replace it with a lookup that won't break — either remove the clause or use a field that still exists.

---

## Step 1.23 — Alembic Migration

**Generate a new migration** that drops the e-commerce tables and columns.

```bash
alembic revision --autogenerate -m "phase1_remove_ecommerce_fields"
```

Expected changes:
- Drop tables: `product_catalog`, `catalog_variants`, `compatibility`, `subscriptions`, `invoices`, `payment_failures`, `policy_sets`, `escalations`, `notification_preferences`
- Drop columns from `customers`: `shopify_customer_id`, `stripe_customer_id`, `recharge_customer_id`, `risk_level`, `sentiment_state`, `sentiment_trend`, `frustration_score`
- Drop columns from `conversations`: `workflow_id`, `workflow_type`, `escalation_id`
- Drop columns from `messages`: `workflow_id`, `workflow_state`
- Add table: `patients`

**WARNING:** This migration is destructive. Ensure database is backed up before running.

---

## Step 1.24 — Verification

After all changes:

```powershell
# 1. Import check
python -c "from app.main import app; print('OK: app imports')"

# 2. Start the server
python -C "import uvicorn; uvicorn.run(app.main:app, host='0.0.0.0', port=8000)"

# 3. Health check
curl http://localhost:8000/health

# 4. Admin panel loads
curl http://localhost:8000/admin/login

# 5. Admin API still works
curl http://localhost:8000/admin/api/settings
```

---

## Dependency Order

Each step must be executed in the correct order. Use this execution sequence:

```
Day 1:
  Step 1.3 → Edit integrations/credentials.py
  Step 1.5 → Delete channels/base.py
  Step 1.6 → Delete channels/rest.py
  Step 1.7 → Delete core/commerce/
  Step 1.9 → Edit config.py
  Step 1.17 → Delete wismo.py
  Step 1.18 → Delete wismo_service.py
  Step 1.20 → Edit core/events/schemas.py
  Step 1.21 → Delete integrations/webhooks.py

Day 2:
  Step 1.1 → Delete integrations/shopify/
  Step 1.4 → Delete integrations/email/
  Step 1.8 → Edit models.py
  Step 1.14 → Edit admin/policies.py
  Step 1.19 → Edit core/workflows/__init__.py
  Step 1.22 → Edit shared/inbox_writer.py

Day 3:
  Step 1.2 → Delete integrations_routes.py
  Step 1.10 → Edit main.py
  Step 1.11 → Edit admin/integrations.py
  Step 1.12 → Edit admin/agents.py
  Step 1.15 → Edit channels/widget.py
  Step 1.16 → Edit templates/
  Step 1.23 → Run Alembic migration
  Step 1.24 → Verify
```

---

## Rollback Plan

If verification fails:

```powershell
# Revert all file changes
git checkout -- api/app/

# Revert database
alembic downgrade -1
```

The migration should have a clear downgrade path that recreates dropped tables.
