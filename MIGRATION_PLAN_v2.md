# Jeeves v2 — Migration Plan

## Overview

**From:** Generic AI support chatbot (LLM-centric orchestrator)
**To:** Deterministic operational workflow infrastructure for subscription commerce

**Nature:** Execution model replacement (~40% reuse, ~60% new build)

### Key architectural shifts

| Current | Target |
|---------|--------|
| `agent.run()` central orchestrator | Workflow Runtime (state machines) |
| Generic tool loop (`routes_tools.py`) | Execution Engine (idempotent actions) |
| Conversational memory (`memory.py`) | Canonical domain entities + Timeline |
| Generic CRM abstraction | Commerce domain adapters (Stripe/Shopify/Recharge) |
| LLM orchestrates everything | AI = bounded assistant (classification, comms only) |
| Chat-first UX | Workflow-driven communication |
| RAG/chunking as core | **🔒 KEEP AS-IS** per instruction |

---

## Codebase Disposition

### ✅ Keep as-is

| File | Notes |
|------|-------|
| `auth.py` | Auth system, JWT, API keys, session cookies |
| `config.py` | Settings + YAML config |
| `db.py` | SQLAlchemy engine + session |
| `crypto.py` | Fernet encryption |
| `rate_limit.py` | Rate limiter (expand Redis usage) |
| `models.py` → `Tenant` | Keep tenant model |
| `alembic/` | Migration framework stays |
| `Dockerfile` | Single-container deploy stays |
| `requirements.txt` | Add `rq`/`arq`, remove unused |
| `moderation.py` | Keep as-is |

### 🔧 Refactor

| File | What to do |
|------|------------|
| `channels/widget.py` | Keep endpoint infra, refactor chat logic → workflow-continuity |
| `channels/registry.py` | Keep O(1) lookup, add email channel type |
| `frontend/widget.js` | Refactor UI: add workflow-aware states (awaiting payment, etc.) |
| `webhooks.py` | Strip incoming webhook → rebuild as part of Event System. Keep HMAC helpers. |
| `connectors/shopify.py` | Refactor from generic → domain adapter (customer, orders, fulfillment) |
| `connectors/stripe_connector.py` | Refactor from generic → domain adapter (invoices, payment retry) |
| `admin.py` + `templates/` | Retain shell, add workflow panels |
| `dashboard_api.py` | Keep stats endpoints, add workflow/analytics endpoints |
| `admin.py` + `templates/` | Retain as UI shell, add workflow/operations panels |
| `billing.py` | Refactor → real Stripe billing implementation |
| `config.yaml` | Update for workflow policies, remove obsolete sections |

### 🗑️ Remove

| File | Reasoning |
|------|-----------|
| `agent.py` | Replaced by Workflow Runtime + AI Assistance layer |
| `actions.py` | Replaced by Execution Engine + Workflow-specific actions |
| `memory.py` | Removed as concept. State lives in domain entities |
| `crm.py` | Generic CRM abstraction removed |
| `hubspot.py` | Not in v2 scope (no generic CRM) |
| `routes_tools.py` | Generic tool CRUD replaced by specific domain tools |
| `rag.py` | **🔒 KEEP AS-IS** — per instruction, RAG stays for now |
| `knowledge.py` | **🔒 KEEP AS-IS** — per instruction, knowledge base stays |
| `chunking.py` | **🔒 KEEP AS-IS** — per instruction, chunking stays |
| `routes_crm.py` | Removed with generic CRM |
| `routes_mock.py` | MVP test mock, remove for v2 |
| `routes_integrations.py` | Replaced by new domain-specific integration endpoints |
| `routes_channels.py` | Replaced by new channel management |
| `routes_api_keys.py` | Keep API key model but separate into new auth structure |
| `connectors/woocommerce.py` | Not in ICP (Shopify-only v2) |
| `connectors/registry.py` | Tool auto-provisioning replaced by domain-specific setup |
| `routes_proactive.py` | Not in v2 scope |
| `routes_chat.py` | Replaced by workflow-driven communication |

### 🆕 New Build

All under `/core/` — see detailed tasks below.

---

## Phase 0: Foundation (prerequisite for all builds)

### 0.1 — Module restructure

Create new directory tree:

```
api/app/
├── core/
│   ├── __init__.py
│   ├── events/
│   ├── workflows/
│   ├── policies/
│   ├── execution/
│   ├── commerce/
│   ├── communications/
│   ├── escalations/
│   ├── timeline/
│   └── ai/
├── channels/
│   ├── __init__.py          # keep
│   ├── widget.py             # refactor
│   ├── email.py              # new
│   ├── registry.py           # keep
│   └── ...
├── integrations/
│   ├── __init__.py
│   ├── stripe/
│   ├── recharge/             # new
│   ├── shopify/
│   └── tracking/             # new
├── workers/
│   ├── __init__.py
│   ├── event_worker.py
│   ├── workflow_worker.py
│   ├── comms_worker.py
│   └── scheduler.py
├── shared/
│   ├── __init__.py
│   ├── db.py                 # keep
│   ├── redis/                # expand
│   ├── locks.py              # new
│   ├── idempotency.py        # new
│   └── queue.py              # new
├── api/                      # routes reorganized
│   ├── __init__.py
│   ├── widget.py
│   ├── webhooks.py
│   ├── admin.py               # keep + extend
│   └── ...
├── templates/                 # keep + add workflow panels
└── main.py                   # rewire imports
```

### 0.2 — Add dependencies

| Library | Purpose |
|---------|---------|
| `rq` or `arq` | Redis-backed background workers |
| `sendgrid` / `resend` / `smtplib` | Email delivery |
| `pydantic` (already have) | Event schemas |

### 0.3 — Alembic migrations for new tables

New tables (see detailed schemas in the v2 `implementation_architecture.md`):

| Table | Purpose |
|-------|---------|
| `customers` | Canonical cross-system customer identity |
| `subscriptions` | Canonical subscription projection |
| `invoices` | Canonical invoice projection |
| `payment_failures` | Operational failure tracking |
| `orders` | Canonical order projection |
| `shipments` | Canonical shipment with tracking |
| `workflows` | Workflow instances |
| `workflow_transitions` | State transition history |
| `canonical_events` | Normalized event store |
| `retry_attempts` | Retry execution log |
| `communications` | Outbound message tracking |
| `escalations` | Escalation/human handoff |
| `timeline_events` | Unified audit trail |
| `ai_interactions` | Bounded AI reasoning artifacts |
| `policy_sets` | Merchant governance policies |

### 0.4 — Redis infrastructure

| Component | Redis Key Pattern |
|-----------|-------------------|
| Workflow locks | `lock:workflow:{id}` |
| Entity locks | `lock:entity:{type}:{id}` |
| Idempotency | `idempotent:{key}` |
| Event dedup | `dedup:event:{id}` |
| Retry schedule | `schedule:retry:{id}` |
| Work queue | `queue:{worker_type}` |

---

## Phase 1: Core Runtime

### 1.1 — Event System (`/core/events/`)

**Files to create:**
- `core/events/__init__.py`
- `core/events/base.py` — `CanonicalEvent` schema
- `core/events/dispatcher.py` — dispatch events to workflows
- `core/events/deduplicator.py` — dedup by `event_id`
- `core/events/schemas.py` — event type definitions

**Tasks:**

| # | Task | Effort |
|---|------|--------|
| 1.1.1 | Define `CanonicalEvent` Pydantic schema (`event_id`, `event_type`, `event_source`, `entity_type`, `entity_id`, `payload`, `occurred_at`) | S |
| 1.1.2 | Build event dispatcher: accept event → validate → dedup → persist to DB → dispatch to workflow runtime | M |
| 1.1.3 | Build event deduplicator (Redis TTL-based): skip if `dedup:event:{id}` exists | S |
| 1.1.4 | Define all canonical event types (`payment_failed`, `payment_recovered`, `subscription_cancel_requested`, `shipment_delayed`, `tracking_updated`, `customer_frustrated`, etc.) | M |
| 1.1.5 | Wire event ingestion endpoints: `POST /api/events/webhooks/stripe`, `POST /api/events/webhooks/recharge`, `POST /api/events/webhooks/shopify` | M |

### 1.2 — Workflow Runtime (`/core/workflows/`)

**Files to create:**
- `core/workflows/__init__.py`
- `core/workflows/runtime.py` — base `Workflow` class
- `core/workflows/registry.py` — `WORKFLOW_REGISTRY` dict + routing
- `core/workflows/transitions.py` — state transition definitions
- `core/workflows/guards.py` — pre-transition validation
- `core/workflows/scheduler.py` — timed execution (retry delay, expiration, cooldown)
- `core/workflows/locks.py` — Redis-based workflow and entity locks

**Tasks:**

| # | Task | Effort |
|---|------|--------|
| 1.2.1 | Define `Workflow` base class: `workflow_id`, `workflow_type`, `current_state`, `handle_event()`, `transition()`, `validate_transition()` | M |
| 1.2.2 | Build `WorkflowRegistry`: maps `workflow_type` → `Workflow` subclass, instantiate and route events | S |
| 1.2.3 | Build transition validator: allowed paths from state machine spec, lock check, policy check, expiration check, escalation check | L |
| 1.2.4 | Build workflow lock manager: Redis `lock:workflow:{id}` with TTL refresh, prevents concurrent workflows of same type per context | M |
| 1.2.5 | Build entity lock manager: Redis `lock:entity:{type}:{id}` per subscription/invoice — prevents concurrent mutations | M |
| 1.2.6 | Build workflow scheduler: polling Redis `schedule:*` for retry/expiration timing, enqueue worker tasks | M |
| 1.2.7 | Build workflow expiration engine: auto-terminate workflows past `expiration_at`, release locks, persist final state | M |
| 1.2.8 | Build shared runtime contracts: `pause()`, `resume()`, `expire()`, `escalate()`, `replay()`, `revalidate()` on base Workflow | L |

### 1.3 — State Machine Engine (`/core/workflows/` continued)

**Tasks:**

| # | Task | Effort |
|---|------|--------|
| 1.3.1 | Define transition maps (from state machine spec) for all 3 workflows as Python dicts with allowed transitions per state | L |
| 1.3.2 | Build generic state machine evaluator: given `(current_state, event) → next_state` with validation chain | M |
| 1.3.3 | Build decision/reason tracking: every transition persists `from_state`, `to_state`, `trigger_event`, `decision_reason`, `policy_snapshot`, `timestamp` | M |

### 1.4 — Timeline Engine (`/core/timeline/`)

**Files to create:**
- `core/timeline/__init__.py`
- `core/timeline/recorder.py`
- `core/timeline/replay.py`
- `core/timeline/queries.py`

**Tasks:**

| # | Task | Effort |
|---|------|--------|
| 1.4.1 | Build timeline recorder: persist `TimelineEvent` (event_type, entity_type, entity_id, payload) on every state transition, action, escalation, communication | M |
| 1.4.2 | Build timeline queries: get_by_workflow(), get_by_customer(), get_by_entity(), time-range filtering, cursor pagination | M |
| 1.4.3 | Build replay engine: given workflow_id, replay all transitions and decisions from `workflow_transitions` + `timeline_events` | L |

### 1.5 — Idempotency System (`/shared/idempotency.py`)

**Tasks:**

| # | Task | Effort |
|---|------|--------|
| 1.5.1 | Build `idempotency_manager.get(key) → result_or_none` and `set(key, result)` with Redis TTL | S |
| 1.5.2 | Define idempotency key format per action type: `payment_retry:{invoice_id}:{attempt}`, `email:{communication_id}`, `subscription_mutation:{sub_id}:{action}` | S |
| 1.5.3 | Integrate idempotency check in Execution Engine (Phase 2) and Communication Engine (Phase 2) | M |

### 1.6 — Worker Framework (`/workers/`)

**Files to create:**
- `workers/__init__.py`
- `workers/base.py` — worker base class
- `workers/event_worker.py`
- `workers/workflow_worker.py`
- `workers/comms_worker.py`
- `workers/scheduler.py`
- `shared/queue.py` — Redis queue abstraction (use RQ or arq)

**Tasks:**

| # | Task | Effort |
|---|------|--------|
| 1.6.1 | Set up RQ/arq integration: Redis-backed task queue | M |
| 1.6.2 | Build event worker: process normalized events → dispatch to workflow runtime | M |
| 1.6.3 | Build workflow worker: execute state transitions, call execution engine | M |
| 1.6.4 | Build scheduler: poll for due retries, expirations, cadence delays | L |

---

## Phase 2: Payment Recovery Workflow

### 2.1 — Commerce Domain Models (`/core/commerce/`)

**Files to create:**
- `core/commerce/__init__.py`
- `core/commerce/customer.py` — `CustomerService`
- `core/commerce/subscription.py` — `SubscriptionService`
- `core/commerce/billing.py` — `InvoiceService`, `PaymentFailureService`

**Tasks:**

| # | Task | Effort |
|---|------|--------|
| 2.1.1 | Build Customer service: canonical customer CRUD, reconcile Shopify/Stripe/Recharge IDs, identity resolution | L |
| 2.1.2 | Build Subscription service: canonical subscription projection, sync from Recharge, pause/skip/delay | L |
| 2.1.3 | Build Invoice/Billing service: canonical invoice projection, sync from Stripe, track payment failures | M |

### 2.2 — Stripe Integration Adapter (`/integrations/stripe/`)

**Files to create:**
- `integrations/stripe/__init__.py`
- `integrations/stripe/client.py`
- `integrations/stripe/events.py` — webhook → canonical event
- `integrations/stripe/actions.py` — retry payment, get invoice, get customer

**Tasks:**

| # | Task | Effort |
|---|------|--------|
| 2.2.1 | Refactor `connectors/stripe_connector.py` → `integrations/stripe/client.py` with clean action interface + idempotency | M |
| 2.2.2 | Build Stripe event ingestor: `stripe/events.py` — normalize webhook payloads → canonical events | M |
| 2.2.3 | Build Stripe action adapter: `retry_payment(invoice_id)`, `get_invoice_state(invoice_id)`, `get_payment_method(customer_id)` | M |

### 2.3 — PaymentRecovery Workflow

**Files to create:**
- `core/workflows/payment_recovery.py` — `PaymentRecoveryWorkflow`

**State machine (from v2 spec):**

```
DETECTED → VALIDATING → CLASSIFYING_FAILURE → SELECTING_STRATEGY
    → OUTREACH_PENDING → OUTREACH_SENT → WAITING_CUSTOMER
    → RETRY_SCHEDULED → RETRY_PENDING → RETRYING → VERIFYING_RESULT
    → RECOVERED | FAILED | ESCALATED | EXPIRED | PAUSED_RECONCILIATION
```

**Tasks:**

| # | Task | Effort |
|---|------|--------|
| 2.3.1 | Implement `PaymentRecoveryWorkflow` subclass: 21 states, full transition map | XL |
| 2.3.2 | Implement DETECTED handler: create workflow, acquire lock, persist snapshot | M |
| 2.3.3 | Implement VALIDATING handler: check invoice unpaid, subscription active, retry eligible, no duplicate, not escalated | M |
| 2.3.4 | Implement CLASSIFYING_FAILURE handler: classify as `recoverable`/`semi_recoverable`/`blocked` (call AI classifier) | M |
| 2.3.5 | Implement SELECTING_STRATEGY handler: deterministic selection of retry timing, outreach timing, communication sequence, escalation thresholds (call Policy Engine) | L |
| 2.3.6 | Implement OUTREACH_PENDING/OUTREACH_SENT handlers: generate comms, validate cadence/dedup, send via Communication Engine | M |
| 2.3.7 | Implement WAITING_CUSTOMER handler: handle events (payment_method_updated, customer_replied, cancel_requested, frustrated, timeout) | L |
| 2.3.8 | Implement RETRY_SCHEDULED/RETRY_PENDING/RETRYING handlers: schedule retry, validate guard conditions, execute via Stripe action | L |
| 2.3.9 | Implement VERIFYING_RESULT handler: reload Stripe invoice state, branch to RECOVERED/FAILED/WAITING_CUSTOMER/PAUSED_RECONCILIATION | M |
| 2.3.10 | Implement PAUSED_RECONCILIATION handler: detect source-of-truth conflicts (Stripe/Recharge desync), revalidate or escalate | M |
| 2.3.11 | Implement terminal states: RECOVERED (close, release locks, update metrics), FAILED, ESCALATED, EXPIRED | M |
| 2.3.12 | Handle all edge cases from v2 spec: duplicate prevention, external payment success, cancellation during recovery, 3DS/SCA auth, frustration detection, concurrent mutations | XL |

### 2.4 — Policy Engine (`/core/policies/`) — partial for retries

**Files to create:**
- `core/policies/__init__.py`
- `core/policies/engine.py` — generic evaluator
- `core/policies/retry_rules.py`

**Tasks:**

| # | Task | Effort |
|---|------|--------|
| 2.4.1 | Build `PolicyEngine.evaluate(policy_type, context) → Decision` — generic rule evaluator | M |
| 2.4.2 | Implement retry policy: `max_attempts`, `retry_windows` (delay array), `cooldown_minutes` | M |
| 2.4.3 | Build retry policy evaluator: given failure category + retry history + policy → retry schedule | M |
| 2.4.4 | Wire policy into SELECTING_STRATEGY state | S |
| 2.4.5 | Build initial communication policy: max outreach count, cooldown between messages, allowed channels per workflow | M |

### 2.5 — Email Delivery (`/core/communications/`) — partial for email

**Files to create:**
- `core/communications/__init__.py`
- `core/communications/service.py`
- `core/communications/templates.py`
- `core/communications/delivery.py`
- `core/communications/deduplication.py`
- `integrations/email/provider.py` — SendGrid / Resend / SMTP adapter

**Tasks:**

| # | Task | Effort |
|---|------|--------|
| 2.5.1 | Set up email provider integration (SendGrid recommended for MVP) | M |
| 2.5.2 | Build email template engine: jinja2 templates for payment update request, retry reminder, authentication assistance | M |
| 2.5.3 | Build delivery tracking: persist `Communication` record with channel, delivery_status, dedup_key | M |
| 2.5.4 | Build message deduplication: check `dedup:{communication_id}` before sending | S |
| 2.5.5 | Build widget message dispatch: POST to widget inbox endpoint (refactor existing `/widget/inbox`) | M |

### 2.6 — AI Assistance Layer — Classifiers (`/core/ai/`) — partial

**Files to create:**
- `core/ai/__init__.py`
- `core/ai/classifier.py`
- `core/ai/sentiment.py`
- `core/ai/generator.py`

**Tasks:**

| # | Task | Effort |
|---|------|--------|
| 2.6.1 | Build failure classifier: classify Stripe failure reason → `recoverable`/`semi_recoverable`/`blocked` | M |
| 2.6.2 | Build sentiment detector: analyze customer message → frustration level (none/low/medium/high) | M |
| 2.6.3 | Build message generator (email): generate customer-friendly payment update request from context + template | M |
| 2.6.4 | Build message generator (widget): same for widget messages (shorter, conversational) | M |
| 2.6.5 | Build AIInteraction recorder: persist every AI call (input, output, confidence) for audit | S |

---

## Phase 3: Cancellation Save Workflow

### 3.1 — Recharge Integration Adapter (`/integrations/recharge/`)

**Files to create:**
- `integrations/recharge/__init__.py`
- `integrations/recharge/client.py`
- `integrations/recharge/events.py`
- `integrations/recharge/actions.py`

**Tasks:**

| # | Task | Effort |
|---|------|--------|
| 3.1.1 | Build Recharge API client: auth, pagination, error handling | M |
| 3.1.2 | Build Recharge event ingestor: normalize subscription events → canonical events | M |
| 3.1.3 | Build Recharge action adapter: `pause_subscription()`, `skip_next_shipment()`, `delay_renewal()`, `cancel_subscription()` | L |

### 3.2 — Shopify Integration Refactor (`/integrations/shopify/`)

**Files to create:**
- `integrations/shopify/__init__.py`
- `integrations/shopify/client.py` (refactored from `connectors/shopify.py`)
- `integrations/shopify/events.py`
- `integrations/shopify/actions.py`

**Tasks:**

| # | Task | Effort |
|---|------|--------|
| 3.2.1 | Refactor `connectors/shopify.py` → `integrations/shopify/client.py` — clean action interface | M |
| 3.2.2 | Build Shopify event ingestor: customer/order webhooks → canonical events | M |
| 3.2.3 | Build Shopify action adapter: `get_customer()`, `get_order()`, `get_fulfillment()` | S |

### 3.3 — CancellationSave Workflow

**File to create:** `core/workflows/cancellation_save.py`

**State machine (from v2 spec):**

```
INTENT_DETECTED → VALIDATING → CLASSIFYING_INTENT → SELECTING_SAVE_FLOW
    → SAVE_OFFER_PENDING → SAVE_OFFER_SENT → WAITING_CUSTOMER_DECISION
    → EXECUTING_ACTION
    → RETAINED | CANCELLED | ESCALATED | FAILED | EXPIRED
```

**Tasks:**

| # | Task | Effort |
|---|------|--------|
| 3.3.1 | Implement `CancellationSaveWorkflow` subclass with full transition map | XL |
| 3.3.2 | Implement INTENT_DETECTED handler: create workflow, freeze duplicate retention attempts, retrieve context | M |
| 3.3.3 | Implement VALIDATING handler: subscription active, save flow enabled, eligible for retention | M |
| 3.3.4 | Implement CLASSIFYING_INTENT handler: classify as `soft_intent`/`hard_intent`/`billing_problem` via AI | M |
| 3.3.5 | Implement SELECTING_SAVE_FLOW handler: select allowed save actions from policy (pause/skip/delay only for MVP) | M |
| 3.3.6 | Implement SAVE_OFFER_PENDING/SENT handlers: generate offer communication, explain options, ensure cancellation path accessible | M |
| 3.3.7 | Implement WAITING_CUSTOMER_DECISION handler: accept/reject/escalate/frustration outcomes | L |
| 3.3.8 | Implement EXECUTING_ACTION handler: reload Recharge state, validate policy, execute pause/skip/delay via Recharge adapter | L |
| 3.3.9 | Implement terminal states: RETAINED, CANCELLED (with compliance logging), ESCALATED, FAILED, EXPIRED | M |
| 3.3.10 | Handle edge cases: regulatory-safe cancellation, prepaid subs, bundle subs, angry customers, refund-linked cancellations | XL |

### 3.4 — Policy Engine — Escalation Rules

**Files to create:**
- `core/policies/escalation_rules.py`
- `core/policies/approval_rules.py`

**Tasks:**

| # | Task | Effort |
|---|------|--------|
| 3.4.1 | Implement escalation policy: thresholds for frustration, repeated failures, conflict detection | M |
| 3.4.2 | Implement approval policy: which actions require merchant approval (discounts, credits, refunds) | M |
| 3.4.3 | Wire policy engine into workflow: prevent disallowed save actions | S |

### 3.5 — Escalation Engine (`/core/escalations/`)

**Files to create:**
- `core/escalations/__init__.py`
- `core/escalations/manager.py`
- `core/escalations/sla.py`
- `core/escalations/assignment.py`

**Tasks:**

| # | Task | Effort |
|---|------|--------|
| 3.5.1 | Build `EscalationManager`: create escalation → pause workflow → track status → resolve → resume workflow | L |
| 3.5.2 | Build SLA timer: time-based escalation (e.g., no response in 24h → requeue) | M |
| 3.5.3 | Build operator assignment queue: assign to human, track ownership | M |
| 3.5.4 | Build shared Escalation state machine: OPEN → ASSIGNED → IN_PROGRESS → WAITING_EXTERNAL → RESOLVED → CLOSED | M |
| 3.5.5 | Wire escalation pause into Workflow runtime: on escalate → `workflow.pause()`, on resolve → `workflow.resume()` | M |

### 3.6 — AI Assistance Layer — Intent Classification

**Tasks:**

| # | Task | Effort |
|---|------|--------|
| 3.6.1 | Build intent classifier: classify customer message → `cancellation_intent` / `wismo` / `billing_question` / `general_support` | M |
| 3.6.2 | Build cancellation intent classifier: `soft_intent` / `hard_intent` / `billing_problem` | M |

---

## Phase 4: WISMO Workflow

### 4.1 — Shipment/Tracking Integration (`/integrations/tracking/`)

**Files to create:**
- `integrations/tracking/__init__.py`
- `integrations/tracking/normalizer.py` — canonical shipment state
- `integrations/tracking/providers/` — carrier adapters (AfterShip, ShipStation, or carrier API)

**Tasks:**

| # | Task | Effort |
|---|------|--------|
| 4.1.1 | Build tracking normalizer: map carrier-specific states → canonical states (`processing`, `fulfilled`, `in_transit`, `delayed`, `exception`, `delivered`, `unknown`) | L |
| 4.1.2 | Build Shopify fulfillment → shipment sync | M |
| 4.1.3 | Build tracking event ingestor: webhooks from AfterShip/ShipStation → canonical events | M |

### 4.2 — Commerce Domain — Shipment (`/core/commerce/shipment.py`)

**Tasks:**

| # | Task | Effort |
|---|------|--------|
| 4.2.1 | Build Shipment service: canonical shipment CRUD, tracking lifecycle, carrier normalization | M |

### 4.3 — WISMO Workflow

**File to create:** `core/workflows/wismo.py`

**State machine (from v2 spec):**

```
INQUIRY_DETECTED → VALIDATING_IDENTITY → RETRIEVING_SHIPMENT
    → NORMALIZING_SHIPMENT_STATE → CLASSIFYING_RISK
    → RESPONSE_PENDING → RESPONSE_SENT → WAITING_CUSTOMER
    → RESOLVED | ESCALATED | FAILED | EXPIRED
```

**Tasks:**

| # | Task | Effort |
|---|------|--------|
| 4.3.1 | Implement `WismoWorkflow` subclass with full transition map | XL |
| 4.3.2 | Implement INQUIRY_DETECTED handler: create workflow, retrieve shipment state, check existing escalations | M |
| 4.3.3 | Implement VALIDATING_IDENTITY handler: order exists, customer verified, shipment data available | M |
| 4.3.4 | Implement RETRIEVING_SHIPMENT handler: fetch from Shopify/tracking provider | M |
| 4.3.5 | Implement NORMALIZING_SHIPMENT_STATE handler: normalize carrier state, validate recency | M |
| 4.3.6 | Implement CLASSIFYING_RISK handler: classify as `simple_wismo`/`delay_concern`/`escalation_risk` via AI | M |
| 4.3.7 | Implement RESPONSE_PENDING/SENT handlers: generate tracking update, ETA, delay explanation (AI generates, system controls) | M |
| 4.3.8 | Implement exception handling: detect stalled shipment, carrier exception, lost package signals → escalate | L |
| 4.3.9 | Implement terminal states: RESOLVED (customer reassured, no escalation), ESCALATED, FAILED, EXPIRED | M |
| 4.3.10 | Handle edge cases: missing tracking data, stale events, split shipments, delivered-but-missing, emotional escalation | XL |

### 4.4 — AI Assistance Layer — WISMO support

**Tasks:**

| # | Task | Effort |
|---|------|--------|
| 4.4.1 | Build WISMO risk classifier: `simple_wismo` / `delay_concern` / `escalation_risk` | M |
| 4.4.2 | Build WISMO response generator: tracking state explanation, ETA, delay reassurance | M |
| 4.4.3 | Build uncertainty-aware messaging: avoid definitive delivery claims when data is stale | M |

---

## Phase 5: Support Continuity & Admin UI

### 5.1 — Lightweight FAQ / Knowledge (`/core/knowledge/`)

**Files to create:**
- `core/knowledge/__init__.py`
- `core/knowledge/service.py`
- `core/knowledge/faq_store.py`

**Tasks:**

| # | Task | Effort |
|---|------|--------|
| 5.1.1 | Simplify knowledge system: remove ChromaDB, remove chunking, remove async indexing | L |
| 5.1.2 | Build simple FAQ store: merchant-defined Q&A pairs in JSONB, keyword + semantic search | M |
| 5.1.3 | Wire FAQ into AI context for continuity questions (policy, shipping, returns) | M |
| 5.1.4 | Keep upload endpoint but store as plain text, not vector-indexed | M |

### 5.2 — Widget Refactor for Workflow Continuity

**Tasks:**

| # | Task | Effort |
|---|------|--------|
| 5.2.1 | Refactor widget inbox: show workflow-related messages (payment update, retry reminder, shipping status) | L |
| 5.2.2 | Add workflow-aware states to widget: "updating payment", "waiting for retry", "checking shipment" | L |
| 5.2.3 | Add inline action buttons: "Update Card", "Track Shipment", "Pause Subscription" | M |
| 5.2.4 | Keep existing chat continuity for non-workflow conversations (FAQ, general questions) | M |

### 5.3 — Admin Dashboard — Workflow Panels

**New templates:**
- `templates/workflows.html`
- `templates/workflow_detail.html`
- `templates/escalations.html`
- `templates/policies.html`
- `templates/timeline.html`
- `templates/analytics.html`

**Tasks:**

| # | Task | Effort |
|---|------|--------|
| 5.3.1 | Build workflow list page: all active workflows per tenant, status, type, customer, started_at, filters | L |
| 5.3.2 | Build workflow detail page: current state, transition history, timeline, communications, escalation status, replay button | XL |
| 5.3.3 | Build escalation queue page: open escalations, assign, resolve, SLA timer | L |
| 5.3.4 | Build policy management page: retry limits, communication cadence, escalation thresholds, approval rules | L |
| 5.3.5 | Build timeline view page: unified operational timeline with filters (event type, entity, date range) | M |
| 5.3.6 | Build workflow replay UI: step through state transitions, see AI decisions, inspect context | L |
| 5.3.7 | Build analytics page: recovered revenue, save rate, churn prevented, avg resolution time, workflow stats | L |
| 5.3.8 | Add workflow section to dashboard navigation | S |

### 5.4 — Billing Implementation

**Tasks:**

| # | Task | Effort |
|---|------|--------|
| 5.4.1 | Implement Stripe billing: customer creation, subscription plans, usage metering | L |
| 5.4.2 | Implement real `_has_payment()`: check Stripe subscription status | M |
| 5.4.3 | Implement usage-based billing: price per resolved workflow, overage tracking | M |
| 5.4.4 | Build billing admin panel: plan info, invoices, payment method | M |

### 5.5 — Cleanup & Removal

**Tasks:**

| # | Task | Effort |
|---|------|--------|
| 5.5.1 | Remove `agent.py`, `actions.py`, `memory.py` — replaced by new architecture | S |
| 5.5.2 | Remove `crm.py`, `hubspot.py` — generic CRM not in scope | S |
| 5.5.3 | Remove `routes_tools.py`, `routes_crm.py`, `routes_mock.py`, `routes_integrations.py`, `routes_proactive.py` | S |
| 5.5.4 | Remove `connectors/woocommerce.py`, `connectors/registry.py` | S |
| 5.5.5 | ~~Simplify `rag.py`, `knowledge.py`, `chunking.py` → lightweight FAQ~~ | **CANCELLED — keep as-is per instruction** |
| 5.5.6 | Update `main.py`: remove old route imports, register new ones | M |
| 5.5.7 | Update `models.py`: keep Tenant, remove unused models, add new ones via new migration | L |
| 5.5.8 | Update `config.yaml`: remove obsolete sections (actions, proactive, generic rag), add policy defaults | M |
| 5.5.9 | Run full test suite, fix regressions | L |

---

## Phase 6: Integration & Deployment

### 6.1 — Testing

| # | Task | Effort |
|---|------|--------|
| 6.1.1 | Build workflow unit tests: state machine transitions, guard conditions, lock acquisition | L |
| 6.1.2 | Build integration tests: Stripe webhook → workflow → communication → resolution | L |
| 6.1.3 | Build edge case tests: duplicate events, external payment success, cancellation during recovery | L |
| 6.1.4 | Build replay/audit tests: verify timeline accuracy, replay produces same result | M |
| 6.1.5 | Build idempotency tests: retry-safe, dedup verification | M |

### 6.2 — Deployment

| # | Task | Effort |
|---|------|--------|
| 6.2.1 | Update Dockerfile: add worker processes, Redis dependency | M |
| 6.2.2 | Update Railway config: add Redis add-on, worker formation | M |
| 6.2.3 | Update `DEPLOY.md`: new env vars (SendGrid API key, Recharge API key, etc.) | S |
| 6.2.4 | Update `.env.example` with new variables | S |
| 6.2.5 | Add health check endpoints for workers | S |

---

## Effort Summary

| Phase | Tasks | Est. Effort |
|-------|-------|-------------|
| Phase 0: Foundation | 15 | 3–4 days |
| Phase 1: Core Runtime | 23 | 2–3 weeks |
| Phase 2: Payment Recovery | 30 | 3–4 weeks |
| Phase 3: Cancellation Save | 30 | 3–4 weeks |
| Phase 4: WISMO | 18 | 2–3 weeks |
| Phase 5: Support Continuity & Admin | 24 | 2–3 weeks |
| Phase 6: Integration & Deployment | 9 | 1 week |
| **Total** | **149 tasks** | **4–5 months** |

## Dependency Graph

```
Phase 0: Foundation
    │
    ▼
Phase 1: Core Runtime
    │
    ├─────────────────────┐
    ▼                     ▼
Phase 2: Payment        Phase 3: Cancellation
Recovery                Save
    │                     │
    └──────────┬──────────┘
               ▼
         Phase 4: WISMO
               │
               ▼
    Phase 5: Support Continuity & Admin
               │
               ▼
    Phase 6: Integration & Deployment
```

Phase 2 and 3 can be built in parallel after Phase 1 is complete. Phase 4 depends on Shopify adapter refactor from Phase 3.

## Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Recharge API complexity underestimated | High | Medium | Build thin adapter first, iterate |
| Stripe webhook reliability (missed events) | High | Medium | Add reconciliation workers (periodic re-check) |
| Worker crashes mid-transition | Medium | Low | Idempotency + replay = safe recovery |
| Email deliverability (bounces, spam) | Medium | High | Start with SendGrid, track delivery status |
| Widget refactor breaks existing tenants | High | Medium | Feature-flag workflow mode vs legacy mode |
| LLM classification accuracy for intent | Medium | Medium | Add confidence threshold → escalate if low |
