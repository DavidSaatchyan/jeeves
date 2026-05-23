# MVP Cleanup Plan

## Focus
- Knowledge Base chat
- WISMO agent (Trace)
- Shopify integration
- Widget + Email channels (WhatsApp — "soon")

## Keep
- **Knowledge Base** — routes, RAG, catalog, chroma
- **Shopify** — full integration: client, actions, events, webhooks
- **Widget** — channel (routes_chat + widget.py)
- **Email** — channel + providers (SendGrid/Resend)
- **WhatsApp** — channels/whatsapp.py (left as-is for "soon")
- **Chat** — routes_chat.py, _simple_llm_response
- **Workflow framework** — runtime.py, registry.py, transitions.py
- **Commerce services** — CustomerService, SubscriptionService, InvoiceService
- **Events dispatcher** — core/events/

## Remove — 7 Blocks

### Block 1: PayGuard + Retain agents
**Delete:**
- `core/workflows/payment_recovery.py` — entire PayGuard workflow (374 lines)
- `core/ai/classifier.py` — `classify_failure()`, only used by PayGuard
- `core/ai/sentiment.py` — `detect_frustration()`, only used by PayGuard
- `core/communications/templates.py` — 4 PayGuard/Retain email templates

**Clean:**
- `core/workflows/registry.py` — remove `route_event()`, `type_to_workflow`, payment_recovery registration
- `core/workflows/transitions.py` — remove `TRANSITION_MAPS` (only had payment_recovery)
- `templates/agents.html` — remove PayGuard, Retain; keep only Trace (WISMO)
- `templates/base.html` — sidebar: remove PayGuard, Retain; Trace as active

### Block 2: Stripe integration
**Delete:**
- `integrations/stripe/__init__.py`
- `integrations/stripe/client.py`
- `integrations/stripe/actions.py`
- `integrations/stripe/events.py`

**Clean:**
- `integrations/webhooks.py` — remove `POST /integrations/webhooks/stripe`
- `integrations_routes.py` — remove `"stripe"` from `_PROVIDERS`, remove `_test_stripe()`
- `admin.py` — remove `PROVIDER_WEBHOOK_EVENTS["stripe"]`, `PROVIDER_REQUIRED_FIELDS["stripe"]`
- `templates/connections.html` — remove Stripe panel + JS validation
- `config.py` — remove `stripe_secret_key`

### Block 3: Recharge integration
**Delete:**
- `integrations/recharge/__init__.py`
- `integrations/recharge/client.py`
- `integrations/recharge/actions.py`
- `integrations/recharge/events.py`

**Clean:**
- `integrations/webhooks.py` — remove `POST /integrations/webhooks/recharge`, `_find_recharge_connector_by_hmac`, `_verify_recharge_hmac`
- `integrations_routes.py` — remove `"recharge"` from `_PROVIDERS`, remove `_test_recharge()`
- `admin.py` — remove `PROVIDER_WEBHOOK_EVENTS["recharge"]`, `PROVIDER_REQUIRED_FIELDS["recharge"]`
- `templates/connections.html` — remove Recharge panel + JS validation
- `config.py` — remove `recharge_api_key`

### Block 4: Telegram channel
**Delete:**
- `channels/telegram.py` (180 lines, broken `agent.run()`)

**Clean:**
- `channels/registry.py` — remove `"telegram"` from `SUPPORTED_CHANNELS`, `CHANNEL_LABELS`, `CHANNEL_DESCRIPTIONS`

### Block 5: Events — unused types
**Clean:**
- `core/events/schemas.py` — remove unused `EVENT_TYPES`: `subscription_cancel_requested`, `subscription_paused/skipped/delayed`, `customer_message_cancellation/wismo/general`, `customer_frustrated`, `shipment_*`, `tracking_updated`, `external_payment_success`

### Block 6: Config
**Clean:**
- `config.py` — remove `stripe_secret_key`, `recharge_api_key` from `Settings`

### Block 7: Scheduler — dead code
**Clean:**
- `core/workflows/scheduler.py` — remove `schedule_job()` function (only used by PayGuard), keep `get_due_jobs()`

## Not Touched
- `core/communications/delivery.py` — email delivery for email channel
- `core/communications/service.py` — `send_communication()` for email channel
- `core/communications/deduplication.py` — general utility
- `integrations/email/` — email provider (SendGrid/Resend)
- `core/commerce/` — CustomerService, SubscriptionService, InvoiceService (needed for WISMO)
- `core/workflows/runtime.py` — Workflow base class
- `core/events/dispatcher.py` — event dispatching
- `channels/whatsapp.py` — left as-is for "soon"
- `channels/widget.py` — MVP widget channel
- `workers/` — all workers
- `integrations/shopify/` — MVP integration

## Execution Order
1. Block 2: Stripe integration
2. Block 3: Recharge integration
3. Block 1: PayGuard + agents
4. Block 4: Telegram channel
5. Block 5: Events cleanup
6. Block 6: Config cleanup
7. Block 7: Scheduler cleanup
8. Templates cleanup (from Blocks 1-3)
9. Test: 287 tests must pass
