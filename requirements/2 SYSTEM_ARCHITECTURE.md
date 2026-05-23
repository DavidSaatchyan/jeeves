# Jeeves — System Architecture Specification

> **Version:** 1.0.0  
> **Status:** Target Architecture  
> **Last updated:** 2026-05-11  

---

## Table of Contents

1. [Architecture Style & Philosophy](#1-architecture-style--philosophy)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Module Dependency Graph](#3-module-dependency-graph)
4. [Platform Structure](#4-platform-structure)
5. [Connector Layer](#5-connector-layer)
6. [Event System](#6-event-system)
7. [Agent Engine](#7-agent-engine)
8. [Workflow Engine](#8-workflow-engine)
9. [Policy Engine](#9-policy-engine)
10. [AI Module](#10-ai-module)
11. [RAG Layer](#11-rag-layer)
12. [Execution Layer](#12-execution-layer)
13. [Channel Layer](#13-channel-layer)
14. [Backend API](#14-backend-api)
15. [Frontend](#15-frontend)
16. [Database](#16-database)
17. [Queue & Jobs](#17-queue--jobs)
18. [Vector Database](#18-vector-database)
19. [Authentication & Authorization](#19-authentication--authorization)
20. [Logging & Observability](#20-logging--observability)
21. [Data Flow](#21-data-flow)
22. [Infrastructure Decisions & Rationale](#22-infrastructure-decisions--rationale)
23. [Key Architectural Rules](#23-key-architectural-rules)

---

## 1. Architecture Style & Philosophy

### 1.1 Style: Modular Monolith

Jeeves is a **modular monolith** — a single deployable unit with strictly separated internal modules (bounded contexts). This is the correct choice for an MVP-stage SMB product:

| Factor | Decision | Rationale |
|--------|----------|-----------|
| **Deployment** | Single container | No operational overhead; one `docker build`, one `docker run` |
| **Module separation** | Python packages with strict imports | `core/` never imports `admin/`; `channels/` never imports `integrations/` |
| **Shared kernel** | Database models, schemas, config | Single source of truth for entities |
| **Worker processes** | Separate containers, same codebase | Scale background processing independently when needed |
| **Future migration** | Extract bounded contexts → microservices | Only if product-market fit justifies complexity |

### 1.2 Philosophical Principles

1. **LLM is a classifier and generator, NOT an executor.** It never changes workflow state, authorizes actions, or calls APIs directly.
2. **Deterministic by default, AI by explicit choice.** Every operational path works without AI. AI is only injected at specific, well-defined points.
3. **Events are the backbone.** External changes → Canonical Events → Workflow Engine. No external system talks to workflows directly.
4. **Policies govern everything.** Merchant configuration always overrides AI suggestions. Policy evaluation is deterministic.
5. **Every action is idempotent.** Retries, messages, mutations, escalations — all must be safe to replay.
6. **Tenant isolation by data, not by process.** All tenants share the same process and database; isolation is via `tenant_id` on every row.

---

## 2. High-Level Architecture

```
                         ┌─────────────────────────────────────────────┐
                         │              Jeeves Platform                │
                         │                                             │
  ┌──────────┐           │  ┌──────────┐    ┌──────────────────────┐   │
  │ Merchant  │           │  │  Admin   │    │    Backend API       │   │
  │ (Browser) │◄──────────│──│  Web UI  │◄──►│  (FastAPI SSR +     │   │
  └──────────┘           │  │(Jinja2)  │    │   JSON Endpoints)    │   │
                          │  └──────────┘    └──────────┬───────────┘   │
  ┌──────────┐           │                              │               │
  │ Customer  │           │  ┌──────────┐               │               │
  │ (Widget)  │◄──────────│──│ Channels │               │               │
  └──────────┘           │  │  Layer   │               │               │
                          │  └────┬─────┘               │               │
  ┌──────────┐           │       │                      │               │
  │ 3rd-party│           │  ┌────▼──────────────────────▼──────────┐    │
  │ Systems  │◄──────────│──┤         Agent Engine                  │    │
  │(Shopify, │           │  │  ┌──────────┐  ┌────────┐  ┌──────┐  │    │
  │ Recharge,│           │  │  │ Workflow │  │ Policy │  │  AI   │  │    │
  │ Stripe)  │           │  │  │  Engine  │  │ Engine │  │Module │  │    │
  └──────────┘           │  │  └────┬─────┘  └────────┘  └──┬───┘  │    │
                          │  │       │                       │       │    │
                          │  │  ┌────▼───────────────────────▼───┐  │    │
                          │  │  │      Execution Layer           │  │    │
                          │  │  │  (idempotent action dispatch)  │  │    │
                          │  │  └────┬───────────────────────────┘  │    │
                          │  │       │                              │    │
                          │  │  ┌────▼───────────────────────────┐  │    │
                          │  │  │      Connector Layer           │  │    │
                          │  │  │  (Shopify, Recharge, Stripe)   │  │    │
                          │  │  └────────────────────────────────┘  │    │
                          │  └──────────────────────────────────────┘    │
                          │                                             │
                          │  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
                          │  │  RAG     │  │   Job    │  │   Auth   │  │
                          │  │  Layer   │  │ Scheduler│  │  Module  │  │
                          │  │(ChromaDB)│  │ (Redis)  │  │  (JWT)   │  │
                          │  └──────────┘  └──────────┘  └──────────┘  │
                          │                                             │
                          │  ┌──────────────────────────────────────┐   │
                          │  │        Data Layer                    │   │
                          │  │  ┌──────────┐  ┌──────────┐         │   │
                          │  │  │PostgreSQL│  │  Redis   │         │   │
                          │  │  │ (source  │  │ (cache,  │         │   │
                          │  │  │  of      │  │  queue,  │         │   │
                          │  │  │  truth)  │  │  locks)  │         │   │
                          │  │  └──────────┘  └──────────┘         │   │
                          │  └──────────────────────────────────────┘   │
                          └─────────────────────────────────────────────┘
```

---

## 3. Module Dependency Graph

The golden rule: **dependencies point INWARD toward the core.** No module depends on a module at its own or outer level.

```
──► = depends on

  ┌──────────────────────────────────────────────────────────────────┐
  │  Admin Web UI  (templates/ )                                      │
  │  │                                                                │
  │  └──► Admin API  (admin.py)                                      │
  │        │                                                          │
  │        ├──► Auth Module  (auth.py)                                │
  │        ├──► Database Models  (models.py)                          │
  │        └──► Agent Engine  (core/)                                 │
  │                                                                   │
  ├──────────────────────────────────────────────────────────────────┤
  │  Channels Layer  (channels/)                                      │
  │  │                                                                │
  │  ├──► Auth Module                                                 │
  │  ├──► RAG Layer                                                   │
  │  └──► AI Module  (core/ai/)                                      │
  │                                                                   │
  ├──────────────────────────────────────────────────────────────────┤
  │  Agent Engine  (core/)  ── THE CORE                               │
  │  │                                                                │
  │  ├──► Event System  (core/events/)                                │
  │  │     └──► Canonical Events                                      │
  │  │                                                                │
  │  ├──► Workflow Engine  (core/workflows/)                          │
  │  │     ├──► Registry, State Machine, Runtime                      │
  │  │     ├──► Scheduler  (shared/queue/)                            │
  │  │     └──► Timeline  (core/timeline/)                            │
  │  │                                                                │
  │  ├──► Policy Engine  (core/policies/)                             │
  │  │     ├──► Retry Rules                                           │
  │  │     ├──► Communication Rules                                   │
  │  │     ├──► Escalation Rules                                      │
  │  │     └──► Approval Rules                                        │
  │  │                                                                │
  │  ├──► AI Module  (core/ai/)                                       │
  │  │     ├──► Classifier (failure, intent, sentiment)               │
  │  │     └──► Generator (email, widget messages)                    │
  │  │                                                                │
  │  ├──► Execution Layer  (core/execution/)                          │
  │  │     ├──► Idempotent Action Dispatch                            │
  │  │     ├──► Guard Conditions                                      │
  │  │     └──► Audit Logging                                         │
  │  │                                                                │
  │  ├──► Commerce Services  (core/commerce/)                         │
  │  │     ├──► Customer Service                                      │
  │  │     ├──► Subscription Service                                  │
  │  │     └──► Billing Service                                       │
  │  │                                                                │
  │  ├──► Communications  (core/communications/)                      │
  │  │     ├──► Message Templates                                     │
  │  │     ├──► Delivery (email, widget inbox)                        │
  │  │     └──► Deduplication                                         │
  │  │                                                                │
  │  └──► Escalations  (core/escalations/)                            │
  │        ├──► State Machine (OPEN→ASSIGNED→...→CLOSED)              │
  │        ├──► SLA Monitoring                                        │
  │        └──► Assignment (round-robin)                              │
  │                                                                   │
  ├──────────────────────────────────────────────────────────────────┤
  │  Connector Layer  (integrations/)                                  │
  │  │                                                                │
  │  ├──► Shopify (client, actions, events)                           │
  │  ├──► Recharge (client, actions, events)                          │
  │  ├──► Stripe (client, actions, events)                            │
  │  └──► Credentials Manager                                           │
  │                                                                   │
  ├──────────────────────────────────────────────────────────────────┤
  │  RAG Layer  (rag.py, chunking.py, knowledge.py)                    │
  │  │                                                                │
  │  ├──► Chunking (PDF/MD/TXT → token-aware chunks)                 │
  │  ├──► Embedding (OpenAI text-embedding-3-small)                  │
  │  ├──► ChromaDB (vector storage + search)                         │
  │  └──► File Management (upload, list, delete, dedup)              │
  │                                                                   │
  └──────────────────────────────────────────────────────────────────┘
```

**Critical dependency rule violations (must be fixed):**

| Current Violation | Problem | Fix |
|-------------------|---------|-----|
| `widget.py` imports `routes_chat._simple_llm_response` | Channel depends on API layer | Move `_simple_llm_response` to `core/ai/base.py` |
| `routes_chat.py` has business logic (increment counters, fire webhooks) | API endpoint has side effects beyond request/response | Move webhook firing and counter increment to core service |
| `knowledge.py` imports `rag` at module level but also locally | Inconsistent import pattern | Standardize on module-level imports |

---

## 4. Platform Structure

### 4.1 Directory Layout (Target)

```
jeeves/
├── api/
│   ├── app/
│   │   ├── main.py              # FastAPI app, router registration, startup
│   │   ├── config.py            # Settings (env vars + config.yaml)
│   │   ├── db.py                # SQLAlchemy engine, session, Base
│   │   ├── models.py            # All ORM models (single source of truth)
│   │   ├── schemas.py           # Pydantic request/response schemas
│   │   │
│   │   ├── admin/               # Admin panel (NOT flat admin.py)
│   │   │   ├── __init__.py      # Router aggregation
│   │   │   ├── auth.py          # Admin login/logout, session
│   │   │   ├── pages.py         # SSR Jinja2 route handlers
│   │   │   ├── api_analytics.py # /admin/api/analytics
│   │   │   ├── api_agents.py    # /admin/api/agents/*
│   │   │   ├── api_settings.py  # /admin/api/settings
│   │   │   ├── api_billing.py   # /admin/api/billing
│   │   │   └── ...
│   │   │
│   │   ├── auth/                # Auth module
│   │   │   ├── __init__.py      # Router: register, login, refresh, revoke
│   │   │   ├── dependencies.py  # get_current_tenant, get_admin_tenant
│   │   │   ├── tokens.py        # JWT issue, decode, revoke
│   │   │   └── api_keys.py      # API key create, hash, verify
│   │   │
│   │   ├── knowledge/           # Knowledge base module
│   │   │   ├── __init__.py      # Router: upload, list, delete, chat, cleanup
│   │   │   ├── files.py         # File management service
│   │   │   └── background.py    # Background indexing
│   │   │
│   │   ├── channels/            # Customer communication channels
│   │   │   ├── __init__.py
│   │   │   ├── base.py          # Abstract channel interface
│   │   │   ├── widget.py        # Web widget: chat, inbox, rating
│   │   │   ├── email.py         # Email channel (SendGrid/Resend)
│   │   │   ├── whatsapp.py      # WhatsApp Business API
│   │   │   └── registry.py      # Channel lookup cache
│   │   │
│   │   ├── chat/                # General chat endpoint (rest_api channel)
│   │   │   ├── __init__.py      # POST /chat
│   │   │   └── service.py       # Chat logic (RAG + LLM)
│   │   │
│   │   ├── core/                # Agent Engine (the core)
│   │   │   ├── __init__.py
│   │   │   ├── ai/              # LLM interactions
│   │   │   ├── events/          # Canonical events, dispatch, dedup
│   │   │   ├── workflows/       # State machines, registry, scheduler
│   │   │   ├── policies/        # Merchant policy evaluation
│   │   │   ├── execution/       # Action dispatch, guards, idempotency, audit
│   │   │   ├── commerce/        # Customer, subscription, invoice services
│   │   │   ├── communications/  # Message templates, delivery, dedup
│   │   │   ├── escalations/     # Escalation state machine, SLA, assignment
│   │   │   └── timeline/        # Audit trail recording and queries
│   │   │
│   │   ├── integrations/        # External service connectors
│   │   │   ├── __init__.py
│   │   │   ├── credentials.py   # Per-tenant credential resolution
│   │   │   ├── webhooks.py      # Stripe/Shopify/Recharge webhook receivers
│   │   │   ├── routes.py        # REST API for managing connectors
│   │   │   ├── shopify/         # Shopify client, actions, events
│   │   │   ├── recharge/        # Recharge client, actions, events
│   │   │   └── stripe/          # Stripe client, actions, events
│   │   │
│   │   ├── rag/                 # RAG subsystem
│   │   │   ├── __init__.py
│   │   │   ├── engine.py        # ChromaDB client, index, search, dedup, purge
│   │   │   └── chunking.py      # Document extraction + token-aware chunking
│   │   │
│   │   ├── shared/              # Cross-cutting infrastructure
│   │   │   ├── queue.py         # Redis-based async task queue
│   │   │   ├── idempotency.py   # Idempotency for external calls
│   │   │   ├── locks.py         # Distributed locks
│   │   │   └── moderation.py    # Content moderation (OpenAI + keyword)
│   │   │
│   │   ├── workers/             # Background worker processes
│   │   │   ├── base.py          # Abstract worker
│   │   │   ├── scheduler.py     # Polls Redis for due jobs
│   │   │   ├── comms.py         # Sends pending communications
│   │   │   ├── workflow.py      # Processes scheduled workflow jobs
│   │   │   └── events.py        # Event queue consumer
│   │   │
│   │   └── templates/           # Jinja2 admin templates
│   │
│   ├── alembic/                 # Database migrations
│   ├── alembic.ini
│   └── requirements.txt
│
├── frontend/
│   ├── widget.js                # Embeddable customer widget
│   ├── widget.css               # Widget styles
│   └── widget.js.gz             # Compressed version for production
│
├── config.yaml                  # Global YAML config (agent prompts, RAG params)
├── Dockerfile                   # Single container build
├── docker-compose.yml           # Local dev (app + postgres + redis + chroma)
└── .env.example                 # Environment variable template
```

### 4.2 Current vs Target: Key Structural Changes

| Current | Target | Rationale |
|---------|--------|-----------|
| `admin.py` (1150 lines) | `admin/` package (split by concern) | Single file is unmaintainable; split into pages + API modules |
| `auth.py` (241 lines) | `auth/` package | Auth has multiple concerns (JWT, API keys, cookies, rate limits) |
| `knowledge.py` + `rag.py` + `chunking.py` (flat) | `knowledge/` + `rag/` packages | Clear separation: file management vs vector search vs chunking |
| `routes_chat.py` (151 lines) | `chat/` package | Chat endpoint should be minimal; business logic moves to core |
| Flat `workers/` | Same (clean) | Already well-structured |
| `shared/` directory | Same (clean) | Already well-structured |

---

## 5. Connector Layer

### 5.1 Purpose

The Connector Layer is the **boundary between Jeeves and external systems**. It provides a uniform interface for:
- Retrieving data from external systems (customers, subscriptions, invoices)
- Executing actions on external systems (payment retries, subscription mutations)
- Receiving and normalizing webhook events

### 5.2 Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Connector Layer                         │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │   Shopify    │  │   Recharge   │  │   Stripe     │   │
│  │              │  │              │  │              │   │
│  │ • client.py  │  │ • client.py  │  │ • client.py  │   │
│  │ • actions.py │  │ • actions.py │  │ • actions.py │   │
│  │ • events.py  │  │ • events.py  │  │ • events.py  │   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘   │
│         │                 │                 │            │
│         └─────────────────┼─────────────────┘            │
│                           │                              │
│                    ┌──────▼──────┐                       │
│                    │ Credentials  │                       │
│                    │  Manager    │                       │
│                    │ (encrypted  │                       │
│                    │  storage)   │                       │
│                    └─────────────┘                       │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │           Webhook Receiver                        │   │
│  │  POST /integrations/webhooks/{stripe|shopify|recharge}│
│  │  ┌──────────┐  ┌──────────┐  ┌────────────────┐  │   │
│  │  │Signature  │  │ Normalize│  │  Dispatch to   │  │   │
│  │  │Verify     │──►│ to       │──►│  Event System  │  │   │
│  │  │           │  │Canonical │  │                │  │   │
│  │  └──────────┘  │ Event    │  └────────────────┘  │   │
│  │                └──────────┘                       │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │           Connector Management API                │   │
│  │  GET    /integrations                             │   │
│  │  POST   /integrations/native                      │   │
│  │  DELETE /integrations/native/{provider}           │   │
│  │  POST   /integrations/native/{provider}/test      │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 5.3 Module Contract: `client.py`

Every connector exports async functions:

```python
# Pattern for all client modules
async def get_<entity>(credentials: dict, entity_id: str) -> dict | None
async def execute_<action>(credentials: dict, params: dict, idempotency_key: str) -> dict
```

Returns structured dicts, never ORM objects. Raises `ConnectorError` on failure.

### 5.4 Module Contract: `events.py`

Every connector exports:

```python
EVENT_TYPE_MAP: dict[str, str]  # External event type → canonical event type

def normalize_webhook(raw_payload: dict, tenant_id: str) -> CanonicalEvent | None
```

### 5.5 Credential Storage

| Field | Storage | Encryption |
|-------|---------|------------|
| API keys / tokens | `NativeConnector.credentials` | Fernet-encrypted JSON string |
| Webhook secrets | `NativeConnector.meta` (JSONB) | Not encrypted (separate from write credentials) |
| Resolved at runtime | `get_credentials(tenant_id, provider)` | Decrypts + returns `dict` |

### 5.6 Connector Capability Matrix

| Operation | Shopify | Recharge | Stripe |
|-----------|---------|----------|--------|
| Get customer | ✅ `get_customer` | — | `get_customer` |
| Get order | ✅ `get_order` | — | — |
| Get subscription | — | ✅ `get_subscription` | — |
| Get invoice | — | — | ✅ `get_invoice` |
| Retry payment | — | — | ✅ `retry_payment` |
| Pause subscription | — | ✅ (via Recharge API) | — |
| Skip subscription | — | ✅ (via Recharge API) | — |
| Get payment method | — | — | ✅ `get_payment_method` |
| Webhook: payment failed | — | ✅ `charge_failed` | ✅ `invoice.payment_failed` |
| Webhook: payment recovered | — | ✅ `charge_success` | ✅ `invoice.payment_succeeded` |
| Webhook: subscription cancelled | — | ✅ | — |

---

## 6. Event System

### 6.1 Purpose

The Event System is the **universal input mechanism** for the Agent Engine. Every external change — payment failure, subscription update, customer message — becomes a `CanonicalEvent` and enters the engine through a single pipeline.

### 6.2 Canonical Event Schema

```python
@dataclass
class CanonicalEvent:
    event_id: str        # UUID hex, generated deterministically for dedup
    tenant_id: str
    event_type: str      # Member of EVENT_TYPES set
    event_source: str    # "stripe", "shopify", "recharge", "system", "chat"
    entity_type: str     # "invoice", "subscription", "customer", "workflow"
    entity_id: str       # External entity ID
    occurred_at: datetime
    payload: dict        # Event-specific data
```

### 6.3 Registered Event Types

| Category | Events |
|----------|--------|
| **Payment** | `payment_failed`, `payment_recovered`, `invoice_payment_failed`, `rebill_failed` |
| **Subscription** | `subscription_cancel_requested`, `subscription_paused`, `subscription_skipped`, `subscription_delayed` |
| **Customer** | `customer_message_cancellation`, `customer_message_general`, `customer_frustrated`, `customer_payment_method_updated` |
| **Shipment** | `shipment_delayed`, `tracking_updated`, `shipment_exception`, `shipment_delivered` |
| **System** | `workflow_timeout`, `manual_escalation`, `external_payment_success` |

### 6.4 Dispatch Pipeline

```
External Webhook or API Call
    │
    ▼
┌─────────────────┐
│ normalize_webhook│  → CanonicalEvent
│ or manual create │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Deduplication   │  → Skip if event_id already processed (5-min window)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  route_event     │  → Map event_type → workflow_type
│  (registry)      │     Find or create workflow instance
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  handle_event    │  → Workflow state machine processes event
│  (workflow)      │     May transition state, execute actions
└─────────────────┘
```

### 6.5 Event-to-Workflow Mapping

```
payment_failed          ──→  payment_recovery
invoice_payment_failed  ──→  payment_recovery
rebill_failed           ──→  payment_recovery
customer_message_cancellation  ──→  cancellation_save (future)
shipment_delayed        ──→  wismo (future)
```

---

## 7. Agent Engine

### 7.1 Purpose

The Agent Engine is the **core of Jeeves**. It orchestrates the Workflow Engine, Policy Engine, AI Module, Execution Layer, and Communications to deliver autonomous agent behavior.

### 7.2 Agent Model

```
┌────────────────────────────────────────────────────────────┐
│                      Agent                                  │
│                                                             │
│  ┌──────────────────┐  ┌────────────────────────────────┐  │
│  │   Metadata        │  │   Workflow Types Supported     │  │
│  │   name            │  │   ["payment_recovery"]         │  │
│  │   description     │  │                                │  │
│  │   status (on/off) │  │   Policy Defaults              │  │
│  │   icon            │  │   retry:   {max:3, windows:[]} │  │
│  └──────────────────┘  │   comms:   {max_outreach:3}    │  │
│                         │   esc:     {threshold: medium} │  │
│  ┌──────────────────┐  └────────────────────────────────┘  │
│  │   Analytics       │                                      │
│  │   30-day stats    │  ┌────────────────────────────────┐  │
│  │   funnel data     │  │   Runtime State                │  │
│  │   active workflows│  │   enabled: bool                │  │
│  └──────────────────┘  │   workflow_count: int           │  │
│                         └────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

### 7.3 Agent Lifecycle

```
Merchant enables agent via Admin UI
    │
    ▼
Agent is registered in DB (policy_set.enabled_workflows)
    │
    ▼
Webhook events for this agent type are now processed
    │
    ▼
Workflows are created, progressed, completed
    │
    ▼
Merchant disables agent
    │
    ▼
Active workflows continue?  ──Yes──→ Complete naturally or expire
    │
    No
    ▼
New events are ignored (no workflow created)
```

### 7.4 Agent Registry (Target)

```python
# core/workflows/registry.py
AGENT_REGISTRY: dict[str, type[Workflow]] = {}  # workflow_type → Workflow class
AGENT_METADATA: dict[str, AgentInfo] = {}        # workflow_type → display info

def register_agent(workflow_type: str, workflow_class: type[Workflow], metadata: AgentInfo):
    """Register an agent type at module import time."""

def get_agent_metadata(workflow_type: str) -> AgentInfo | None
def list_enabled_agents(tenant_id: str, db) -> list[AgentInfo]
def list_all_agents() -> list[AgentInfo]
```

Only `payment_recovery` is registered in MVP.

---

## 8. Workflow Engine

### 8.1 Purpose

The Workflow Engine manages **deterministic state machines** for business processes. Each workflow instance tracks a specific business process (e.g., recovering a specific failed payment) through a predefined set of states.

### 8.2 State Machine Contract

Every workflow:

```python
class Workflow(ABC):
    workflow_type: str          # "payment_recovery"
    tenant_id: UUID
    customer_id: str
    current_state: str
    status: str                 # active | paused | completed | escalated
    expiration_at: datetime

    @abstractmethod
    async def handle_event(self, event: CanonicalEvent, db) -> None:
        """Route event to current state handler. Never called directly by external code."""

    def transition(self, to_state: str, event: CanonicalEvent | None, db, reason: str) -> None:
        """Validate + persist state transition. Records to timeline."""

    def pause(self, db) -> None
    def resume(self, db) -> None
    def expire(self, db) -> None
    def escalate(self, db, reason: str) -> None
```

### 8.3 Supported Runtime Operations

| Operation | Description | Idempotent |
|-----------|-------------|------------|
| `pause()` | Pause automation, release escalation | ✅ |
| `resume()` | Resume paused workflow | ✅ |
| `expire()` | Safely terminate due to timeout | ✅ |
| `escalate()` | Create escalation, pause workflow | ✅ |
| `replay()` | Re-run current state handler | ✅ (via idempotency) |
| `revalidate()` | Re-check preconditions from source of truth | ✅ |

### 8.4 Transition Validation

Every transition runs through:

```
transition(to_state, event, db, reason)
    │
    ├── 1. validate_transition(current_state, to_state)
    │      → Checks TRANSITION_MAPS[workflow_type][current_state]
    │
    ├── 2. acquire_workflow_lock(db)
    │      → Prevents concurrent mutations
    │
    ├── 3. check_policy_compliance(db, to_state)
    │      → Policy engine approves/rejects
    │
    ├── 4. check_source_of_truth(db)
    │      → Re-validate canonical state
    │
    ├── 5. record_transition(db, from, to, event, reason, policy_snapshot)
    │      → Persist to workflow_transitions + timeline_events
    │
    ├── 6. update_workflow(db, current_state=to_state)
    │      → Set status = completed if terminal, paused if escalated
    │
    └── 7. release_workflow_lock(db)
```

### 8.5 PayGuard State Machine (Payment Recovery)

```
                    DETECTED
                        │
                        ▼
                   VALIDATING
                   ┌──┴──┐
                   │     │
                   ▼     ▼
               FAILED  CLASSIFYING_FAILURE
                          │
                    ┌─────┴─────┐
                    │           │
                    ▼           ▼
            SELECTING_STRATEGY  ESCALATED
               ┌────┴────┐
               │         │
               ▼         ▼
         OUTREACH_PENDING  RETRY_SCHEDULED
               │              │
               ▼              ▼
          OUTREACH_SENT    RETRY_PENDING
               │              │
               ▼              ▼
          WAITING_CUSTOMER  RETRYING
           ┌──┴──┐            │
           │     │            ▼
           ▼     ▼        VERIFYING_RESULT
     ESCALATED  RETRY    ┌──┴──┬──┴──┐
                SCHEDULED │     │     │
                         ▼     ▼     ▼
                     RECOVERED WAITING PAUSED_
                              CUSTOMER RECONCILIATION
                                         │
                                         ▼
                                     VALIDATING (loop)
```

### 8.6 State Handlers: Implementation Pattern

```python
class PaymentRecoveryWorkflow(Workflow):
    workflow_type = "payment_recovery"

    HANDLERS: dict[str, Callable] = {
        "DETECTED": _handle_detected,
        "VALIDATING": _handle_validating,
        "CLASSIFYING_FAILURE": _handle_classifying_failure,
        "SELECTING_STRATEGY": _handle_selecting_strategy,
        "OUTREACH_PENDING": _handle_outreach_pending,
        # ...
    }

    async def handle_event(self, event, db):
        handler = self.HANDLERS.get(self.current_state)
        if not handler:
            raise RuntimeError(f"No handler for state {self.current_state}")
        await handler(self, event, db)
```

Each handler:
1. Receives event + db session
2. Calls deterministic services (policy engine, commerce services)
3. Optionally calls AI (classification, generation)
4. Calls `self.transition(to_state, event, db, reason)` to move to next state
5. Never makes side effects directly — always through `core/execution/`

---

## 9. Policy Engine

### 9.1 Purpose

The Policy Engine is the **governance layer** that constrains agent behavior according to merchant configuration. Every operational decision passes through it.

### 9.2 Architecture

```
merchant configures policies via Admin UI
    │
    ▼
PolicySet stored in DB (JSONB columns)
    │
    ▼
PolicyEngine(tenant_id, db) loads from DB or defaults
    │
    ▼
Workflow calls policy_engine.evaluate("retry", context)
    │
    ▼
Returns: {allowed: bool, delay_seconds: int, reason: str}
```

### 9.3 Policy Domains

| Domain | Evaluates | Returns |
|--------|-----------|---------|
| **Retry** | attempt_count, failure_category, subscription_value | `{should_retry, delay_seconds, max_attempts}` |
| **Communication** | channel, outreach_count, hours_since_last | `{allowed, cooldown_hours, max_outreach}` |
| **Escalation** | frustration_level, failure_count, amount, is_duplicate | `{should_escalate, reason}` |
| **Approval** | action_type, context | `{requires_approval, allowed_actions}` |

### 9.4 Default Policies (MVP)

```yaml
retry:
  max_attempts: 3
  retry_windows_seconds: [300, 3600, 86400]   # 5 min, 1 hr, 24 hr
  cooldown_minutes: 5

communication:
  max_outreach_per_workflow: 3
  cooldown_between_messages_hours: 24
  allowed_channels: ["email", "widget"]

escalation:
  frustration_threshold: "medium"
  max_failures_before_escalation: 3
  sla_hours: 24

approval:
  requires_approval: []  # None in MVP (approvals system not built)
  allowed_save_actions: ["pause", "skip", "delay"]
```

### 9.5 Integration Points

| Workflow State | Policy Check | Engine Call |
|---------------|-------------|-------------|
| `VALIDATING` | Is retry allowed at all? | `evaluate("retry", {attempt_count: 0})` |
| `SELECTING_STRATEGY` | Compute retry schedule | `evaluate("retry", {attempt_count, category})` |
| `OUTREACH_PENDING` | Can we send a message? | `evaluate("communication", {channel, count, hours})` |
| `WAITING_CUSTOMER` | Should we escalate? | `evaluate("escalation", {frustration, failures})` |
| `RETRY_PENDING` | Is retry still valid? | `evaluate("retry", {attempt_count, ...})` |

---

## 10. AI Module

### 10.1 Purpose

The AI Module is the **bounded non-deterministic component**. It handles tasks that genuinely require language understanding and generation. It NEVER controls workflow state, authorizes actions, or executes operations.

### 10.2 Strict Boundary

```
┌──────────────────────────────────────────────────────────┐
│                   AI Module                               │
│                                                            │
│  ALLOWED:                         FORBIDDEN:               │
│  ┌──────────────────────┐        ┌────────────────────┐   │
│  │ • classify_failure   │        │ • change workflow  │   │
│  │ • detect_frustration │        │   state            │   │
│  │ • generate_email     │        │ • authorize        │   │
│  │ • generate_widget_msg│        │   execution        │   │
│  │ • generate_response  │        │ • schedule retries │   │
│  └──────────────────────┘        │ • perform actions  │   │
│                                   │ • make policy      │   │
│                                   │   decisions        │   │
│                                   └────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

### 10.3 AI Operations

| Operation | Model | Temperature | Max Tokens | Input | Output |
|-----------|-------|-------------|-------------|-------|--------|
| `classify_failure` | gpt-4o-mini | 0.1 | 200 | failure reason + code | `{category, confidence, explanation}` |
| `detect_frustration` | gpt-4o-mini | 0.1 | 150 | customer message | `{level, confidence, indicators}` |
| `generate_email` | gpt-4o-mini | 0.3 | 300 | context + template name | `{subject, body}` |
| `generate_widget_message` | gpt-4o-mini | 0.3 | 150 | context + template name | `{message}` |
| `generate_chat_response` | gpt-4o-mini | 0.3 | 1000 | message + RAG context + history | response text |

### 10.4 Error Handling

Every AI call has a deterministic fallback:

| Operation | Fallback |
|-----------|----------|
| `classify_failure` | Return `recoverable` with confidence 0.0, log error |
| `detect_frustration` | Return `none` level, log error |
| `generate_email` | Use static template text, log error |
| `generate_widget_message` | Use static template text, log error |
| `generate_chat_response` | Return "I'm having trouble connecting. Please try again." |

### 10.5 Migration: Current Issue

Currently `_simple_llm_response()` lives in `routes_chat.py` and is imported by `widget.py`. This is a dependency direction violation. Target:

```
routes_chat.py  ──calls──►  core/ai/base.py:generate_chat_response()
widget.py       ──calls──►  core/ai/base.py:generate_chat_response()
                              ▲
                              │
                    ┌─────────┴─────────┐
                    │                   │
              classify_failure    detect_frustration
              generate_email      generate_widget_message
```

---

## 11. RAG Layer

### 11.1 Purpose

The RAG Layer enables Jeeves to answer customer questions using the merchant's own documentation (knowledge base). It is used exclusively by the Channels Layer (widget chat, email replies) and is NOT part of the Agent Engine.

### 11.2 Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                          RAG Layer                                │
│                                                                   │
│  ┌──────────────────────┐    ┌────────────────────────────────┐  │
│  │  File Management      │    │     Vector Pipeline            │  │
│  │  (knowledge/)         │    │     (rag/)                     │  │
│  │                       │    │                                │  │
│  │  Upload → validate    │    │  index_file():                 │  │
│  │         → dedup hash  │    │    chunk → embed → store      │  │
│  │         → save to disk│    │                                │  │
│  │         → background  │    │  search():                     │  │
│  │           index       │    │    embed query → Chroma query  │  │
│  │                       │    │    → dedup → threshold → return│  │
│  │  List / Delete        │    │                                │  │
│  │  Cleanup (orphans)    │    │  delete_file():                │  │
│  └──────────────────────┘    │    remove chunks by file_id    │  │
│                                └────────────────────────────────┘  │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │  Chunking (chunking.py)                                       │ │
│  │                                                                │ │
│  │  .txt:  whole file → token-aware recursive split              │ │
│  │  .md:   heading-aware split → section path in metadata        │ │
│  │  .pdf:  per-page extract → per-page chunk → section path      │ │
│  │                                                                │ │
│  │  Budget: MAX_TOKENS=512, OVERLAP=64, HARD_CAP=1800            │ │
│  │  Strategy: paragraphs → sentences → hard token window         │ │
│  └──────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

### 11.3 Data Flow: Upload to Search

```
1. Merchant uploads file via Admin UI POST /knowledge/files
    │
    ▼
2. knowledge.py:
   a. Validate extension (.txt, .pdf, .md)
   b. Check content_hash (SHA-256) for duplicates
   c. Check storage quota (50 MB/tenant)
   d. Save file to disk: {knowledge_dir}/{tenant_id}/{file_id}/{filename}
   e. Create FileRecord in DB (status="processing")
   f. Spawn asyncio.create_task(_background_index)
    │
    ▼
3. Background index:
   a. chunking.build_chunks(path) → list[Chunk]
      - Extract units (MD headings, PDF pages, TXT whole)
      - Recursive split: paragraphs → sentences → token window
      - Prepend section path: "# Section\n\nchunk text"
      - Generate deterministic chunk_hash (SHA1 of chunk text)
      - Return Chunk objects with metadata (filename, section, page, char offsets)
    │
    ▼
   b. rag.index_file(tenant_id, file_id, path)
      - Get or create Chroma collection: "tenant_{uuid_nodashes}"
      - Delete old chunks for same file_id (idempotent reindex)
      - Embed all chunks via OpenAI text-embedding-3-small
      - Store in Chroma with IDs: "{file_id}-{i}-{chunk_hash}"
      - Store metadata: file_id, filename, section, page, char_start, char_end, chunk_hash
    │
    ▼
   c. Update FileRecord: status="ready", chunks_total=n
    │
    ▼
4. Customer sends message via widget:
    │
    ▼
5. rag.search(tenant_id, query, top_k=15, threshold=0.85)
   a. Embed query via OpenAI text-embedding-3-small
   b. Chroma query: n_results=top_k, include=["documents","metadatas","distances"]
   c. Deduplicate by chunk_hash (keep first occurrence)
   d. If best distance > threshold → return [] (no relevant context)
   e. Log all returned chunks (filename, section, distance, score, text preview)
   f. Return list[dict]: {id, text, distance, score, file_id, filename, section, page, chunk_hash}
    │
    ▼
6. Channel builds system prompt:
   - If context found: "Answer using ONLY the context below..."
   - If no context: "You don't have this information. Offer specialist."
    │
    ▼
7. LLM generates response with RAG context
    │
    ▼
8. Response returned to customer
```

### 11.4 Collection Isolation

Each tenant has a separate Chroma collection:

```python
def _collection(tenant_id):
    name = f"tenant_{str(tenant_id).replace('-', '')}"
    return chroma.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )
```

### 11.5 Configuration

```yaml
rag:
  embedding_model: "text-embedding-3-small"
  top_k: 15              # Number of chunks to retrieve
  distance_threshold: 0.85  # Cosine distance threshold (lower = stricter)
  chunk_size: 512        # Target tokens per chunk
  chunk_overlap: 64      # Overlap tokens between sliding windows
```

---

## 12. Execution Layer

### 12.1 Purpose

The Execution Layer ensures that **every operational action** is executed safely, exactly once (or zero times), and is fully auditable.

### 12.2 Execution Contract

```python
async def execute_action(
    action_fn: Callable,          # The actual API call (e.g., stripe.retry_payment)
    action_name: str,             # "retry_payment", "send_email"
    idempotency_key: str,        # Deterministic key
    guard_conditions: list[Guard], # Pre-execution checks
    *args, **kwargs
) -> ActionResult:
    """
    1. Check guard conditions (all must pass)
    2. Check idempotency (skip if already done)
    3. Execute action
    4. Record audit log
    5. Return result
    """
```

### 12.3 Idempotency Strategy

| Scope | Key Generation | Storage | TTL |
|-------|---------------|---------|-----|
| Payment retry | `retry:{tenant_id}:{invoice_id}:{attempt}` | Redis (in-memory fallback) | 24h |
| Email send | `comms:{tenant_id}:{communication_id}` | Redis (in-memory fallback) | 24h |
| Subscription mutation | `sub_mut:{tenant_id}:{sub_id}:{action}:{timestamp_window}` | Redis (in-memory fallback) | 1h |
| Escalation create | `esc:{tenant_id}:{workflow_id}` | DB unique constraint | Permanent |

### 12.4 Guard Conditions

Every action checks before execution:

```python
@dataclass
class Guard:
    condition: Callable[[], bool]  # Must return True to pass
    reason: str                     # Human-readable failure reason
    severity: str                   # "warn" | "block"
```

Example guards for `retry_payment`:
- `subscription_is_active()` — block if cancelled
- `invoice_is_unpaid()` — block if already paid
- `retry_limit_not_exceeded()` — block if max attempts reached
- `no_external_payment_since()` — block if customer paid manually

### 12.5 Audit Log

Every execution records:

```python
{
    "action": "retry_payment",
    "workflow_id": "...",
    "tenant_id": "...",
    "idempotency_key": "...",
    "status": "success" | "failure" | "skipped_duplicate" | "blocked",
    "request": {...},       # Action parameters
    "response": {...},      # API response (masked)
    "error": "...",         # Error message if failed
    "latency_ms": 1234,     # Execution time
    "guard_results": [...], # Which guards passed/failed
    "created_at": "...",
}
```

---

## 13. Channel Layer

### 13.1 Purpose

The Channel Layer provides a **uniform abstraction** for communicating with end customers across different mediums (widget, email, WhatsApp).

### 13.2 Channel Interface

```python
class Channel(ABC):
    channel_type: str   # "web_widget", "email", "whatsapp"

    @abstractmethod
    async def send(self, recipient: str, message: str, context: dict) -> SendResult: ...

    @abstractmethod
    async def receive(self, payload: dict) -> IncomingMessage | None: ...

    @abstractmethod
    def validate_config(self, config: dict) -> list[str]:  # Returns errors
```

### 13.3 Channel Registry

Thread-safe cache built on startup from `channels_config` table:

```
Startup: build_channel_cache(db)
  → For each active channel config:
    → phone_number → tenant_id  (whatsapp)
    → tenant_id → allowed_origins  (widget)

Invalidated on: channel create, update, delete
```

### 13.4 Channel Capabilities Matrix

| Capability | Widget | Email | WhatsApp |
|-----------|--------|-------|----------|
| Inbound chat | ✅ | ❌ (future) | ✅ |
| Outbound proactive | ✅ (inbox) | ✅ | ✅ |
| Rich formatting | ❌ | ✅ (HTML) | ✅ (Markdown) |
| Attachments | ❌ | ✅ | ✅ |
| Message history | ✅ (localStorage) | ❌ | ❌ |
| Rate limiting | 20/min/IP | Policy-governed | Policy-governed |
| Authentication | Origin validation | SPF/DKIM | Business account |
| MVP | ✅ | ✅ | ✅ |

### 13.5 Inbound Message Flow

```
Customer sends message via channel
    │
    ▼
Channel-specific webhook/endpoint
    │
    ▼
1. Resolve tenant (from channel registry)
2. Validate signature/origin/auth
3. Moderate content (OpenAI + keyword)
4. Check rate limit
    │
    ▼
┌─── RAG search (if chat) ──→ Build system prompt with context
│
▼
┌─── AI generate response ──→ Log to ChatLog
│
▼
Return response to channel
```

### 13.6 Outbound (Proactive) Message Flow

```
Workflow state handler calls send_communication()
    │
    ▼
1. Check communication policy:
   - outreach limit not exceeded
   - cooldown elapsed
   - channel allowed
2. Check deduplication
3. Generate content (AI or template)
4. Send via channel
5. Record in communications table
6. Record timeline event
```

---

## 14. Backend API

### 14.1 Router Structure

| Prefix | Module | Auth | MVP |
|--------|--------|------|-----|
| `/` | `main.py` (landing, health, legal) | None | ✅ |
| `/auth/*` | `auth/` | None (register/login) / JWT | ✅ |
| `/admin/*` | `admin/` | Session cookie | ✅ |
| `/admin/api/*` | `admin/` (JSON API) | Session cookie | ✅ |
| `/knowledge/*` | `knowledge/` | JWT / API key | ✅ |
| `/chat` | `chat/` | JWT / API key | ✅ |
| `/widget/*` | `channels/widget.py` | Origin validation | ✅ |
| `/integrations/*` | `integrations/` | JWT / API key | ✅ |
| `/integrations/webhooks/*` | `integrations/webhooks.py` | Signature verification | ✅ |

### 14.2 API Design Principles

1. **JSON for everything** (except widget.js and file upload)
2. **Consistent error format:** `{"detail": "message"}` with appropriate HTTP status
3. **Cursor pagination** for large lists (logs, workflows)
4. **Admin API returns flat objects** — no nested serialization (frontend assembles views)
5. **Webhook receivers return 200 immediately** — processing is async

---

## 15. Frontend

### 15.1 Admin Panel (SSR Jinja2)

| Page | Route | Purpose |
|------|-------|---------|
| Login | `/admin/login` | Auth |
| Agents | `/admin/agents` | Agent dashboard, analytics, queue, policy config |
| Knowledge | `/admin/knowledge` | File upload, list, delete; inline widget test |
| Connections | `/admin/connections` | Connect/disconnect Shopify, Recharge, Stripe |
| Channels | `/admin/channels` | Widget config, email SMTP, WhatsApp |
| Settings | `/admin/settings` | API keys, notification prefs |
| Account | `/admin/account` | Plan info, billing usage |

### 15.2 Customer Widget (Vanilla JS)

- **Self-contained:** IIFE with Shadow DOM for style isolation
- **Configuration:** HTML `data-*` attributes on the script tag
- **State:** localStorage (messages, identity, seen inbox IDs)
- **API:** `POST /widget/chat`, `GET /widget/inbox`, `POST /widget/rating`
- **Proactive:** Polls `/widget/inbox` every 15 seconds
- **Rating:** Follow-up card after 3 min inactivity
- **No build step:** Served directly as `/widget.js`

### 15.3 Frontend Architecture Rules

1. **No SPA framework** — Jinja2 SSR + vanilla JS for MVP
2. **API calls go through `api()` helper** — auto-includes Bearer token, handles 401/402
3. **Sensitive actions get confirmation modals** — never execute without user acknowledgment
4. **Errors are displayed inline** — no alert() dialogs
5. **Forms submit via fetch** — no traditional POST redirects

---

## 16. Database

### 16.1 Schema

See [PRD Section 4](PRD.md#4-domain-entities) for full entity definitions.

### 16.2 Connection Management

```python
# db.py — single engine, single session factory
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,      # Detect stale connections
    pool_size=10,            # Connection pool size
    max_overflow=20,         # Additional connections under load
    pool_recycle=3600,       # Recycle connections hourly
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
```

### 16.3 Migration Strategy

- **Tool:** Alembic
- **Run:** On every container startup (in `main.py` `on_startup`)
- **Dev fallback:** SQLite + `Base.metadata.create_all()` when JSONB → JSON
- **Naming convention:** `{revision}_{description}.py`

### 16.4 Dev/Prod Parity

| Feature | Development | Production |
|---------|-------------|------------|
| Database | SQLite (`jeeves_dev.db`) | PostgreSQL (Railway) |
| Vector DB | Chroma persistent (`/data/chroma`) | Chroma HTTP (sidecar) |
| Redis | In-memory fallback | Redis Cloud |
| Config | `.env` file | Railway env vars |

### 16.5 JSONB Compatibility

Models use `JSONB = JSON` to support both PostgreSQL JSONB and SQLite JSON. In production, the raw SQL column type is JSONB; in development, it's JSON. This is handled transparently by SQLAlchemy.

---

## 17. Queue & Jobs

### 17.1 Purpose

Background processing for:
- Scheduled workflow retries (e.g., "retry in 5 minutes")
- Pending communication delivery
- Event queue consumption

### 17.2 Architecture (Target)

```
┌──────────────────────────────────────────────────────────────┐
│                     Job Scheduler                             │
│                                                              │
│  schedule_job(type, execute_at, payload)                     │
│       │                                                      │
│       ▼                                                      │
│  Redis: ZADD schedule:index {timestamp → key}               │
│  Redis: SET schedule:{type}:{uuid} {payload} EX {ttl}       │
│                                                              │
│       ▲                                                      │
│       │                                                      │
│  SchedulerWorker (polls every 5s)                            │
│  ZRANGEBYSCORE schedule:index 0 {now}                        │
│  → GET each key → dispatch → ZREM + DEL                      │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                     Async Task Queue                          │
│                                                              │
│  enqueue(queue_name, payload)                                │
│       │                                                      │
│       ▼                                                      │
│  Redis: RPUSH queue:{name} {payload}                        │
│                                                              │
│       ▲                                                      │
│       │                                                      │
│  Worker: LPOP queue:{name} → handler(payload)               │
│  (polling or BLPOP)                                          │
└──────────────────────────────────────────────────────────────┘
```

### 17.3 Job Types

| Job Type | Scheduled By | Worker | Purpose |
|----------|-------------|--------|---------|
| `retry_payment` | Workflow Engine | `workflow_worker` | Execute payment retry at scheduled time |
| `workflow_timeout` | Workflow creation | `workflow_worker` | Expire workflow after 7 days |
| `send_communication` | Workflow Engine | `comms_worker` | Send pending email/widget messages |
| `recheck_invoice` | Workflow Engine | `workflow_worker` | Re-check Stripe invoice state |

### 17.4 Redis Fallback

All queue/scheduler functions have graceful fallback:

```python
if not _use_redis:
    logger.warning("Redis not configured — job scheduling disabled")
    return None  # or [] for get_due_jobs
```

This means without Redis:
- Retry scheduling is disabled
- Workflows proceed directly (no delayed retries)
- Communications are sent synchronously

---

## 18. Vector Database

### 18.1 Technology: ChromaDB

**Why ChromaDB (not Pinecone, Weaviate, Qdrant):**
- **Embeddable:** Can run as persistent client (no separate service) in dev
- **Simple API:** `add()`, `query()`, `delete()` — minimal learning curve
- **Self-hosted:** No API costs, no data leaves infrastructure
- **Sufficient for MVP:** 100K chunks per tenant is plenty for SMB

### 18.2 Collection Layout

| Property | Value |
|----------|-------|
| Collection name | `tenant_{uuid_nodashes}` |
| Distance metric | Cosine |
| Embedding model | `text-embedding-3-small` (1536 dimensions) |
| Schema version | Embedded in collection metadata (`embedding_version`) |

### 18.3 Chunk Metadata Schema

```python
{
    "file_id": str,          # UUID of the FileRecord
    "filename": str,         # Original filename
    "section": str,          # Section path: "Pricing > Business plan"
    "page": int | None,      # PDF page number (1-based)
    "char_start": int,       # Character offset in source
    "char_end": int,         # Character offset in source
    "chunk_hash": str,       # SHA1 of chunk text (for dedup)
}
```

### 18.4 Chunk ID Schema

```
{file_id}-{chunk_index}-{chunk_hash}
```

Example: `550e8400-e29b-41d4-a716-446655440000-3-a1b2c3d4e5f6`

This makes re-indexing idempotent: same file + same content = same chunk IDs → Chroma's upsert behavior overwrites.

### 18.5 Storage Estimation

| Metric | Per file (10-page PDF) | Per tenant (50 MB) |
|--------|----------------------|---------------------|
| Chunks | ~30 | ~10,000 |
| Embedding size | 30 × 1536 × 4B = 184 KB | 10,000 × 6 KB = 60 MB |
| Metadata | Negligible | Negligible |

---

## 19. Authentication & Authorization

### 19.1 Auth Methods

| Method | Where Used | Mechanism |
|--------|-----------|-----------|
| JWT Bearer token | API endpoints | HS256, 15min TTL |
| Session cookie | Admin UI pages | httponly, samesite=lax, path=/admin |
| Refresh token | `/auth/refresh` | HS256, 30 day TTL |
| API key | Server-to-server | `sk_` prefix, HMAC-SHA256 hashed |

### 19.2 Token Flow

```
Registration / Login
    │
    ▼
Issue: access_token (15min) + refresh_token (30day)
    │
    ├── API client: stores tokens, uses Bearer header
    │
    └── Browser: access_token set as session cookie
                   refresh_token stored in localStorage
                   Auto-refresh via /auth/refresh
```

### 19.3 API Key Flow

```
Merchant creates key in Admin UI → raw key shown once
    │
    ▼
Key stored as: HMAC-SHA256(raw_key, pepper) → SHA256 → key_hash
    │
    ▼
Client uses: Authorization: Bearer sk_abc123...
    │
    ▼
Server: Extract prefix (sk_abc), look up by hash, validate HMAC
```

### 19.4 Role Model (MVP)

| Role | Access Level | Implementation |
|------|-------------|----------------|
| Owner | Full access to everything | All authenticated users (no role check) |

### 19.5 Session Management for Workers

Worker processes use a **background service account** pattern:

```python
# workers use direct DB sessions, not API tokens
from app.db import SessionLocal
db = SessionLocal()
try:
    # ... processing logic
finally:
    db.close()
```

---

## 20. Logging & Observability

### 20.1 Log Levels

| Module | Level | Details |
|--------|-------|---------|
| HTTP requests | INFO | method, path, masked body |
| Auth | WARNING | Failed login attempts, invalid tokens |
| Workflow transitions | INFO | workflow_id, from_state, to_state, reason |
| AI calls | INFO | input preview, output summary, latency, tokens |
| RAG search | INFO | query, result count, best distance, filenames |
| Webhooks received | INFO | provider, event_type, tenant_id |
| Background jobs | INFO | job_type, job_id, status |
| Errors | ERROR | Full traceback |

### 20.2 Audit Events (Timeline)

Every meaningful business event is recorded in `timeline_events`:

| Event Type | Trigger | Payload |
|-----------|---------|---------|
| `workflow_created` | Workflow creation | tenant_id, workflow_type, customer_id |
| `workflow_transition` | State change | from, to, reason, policy_snapshot |
| `workflow_completed` | Terminal state | final_state, duration |
| `comms_sent` | Communication sent | channel, template, recipient |
| `escalation_created` | Escalation | reason, severity |
| `escalation_resolved` | Resolution | resolution_note |
| `retry_executed` | Payment retry | attempt, result, latency |
| `policy_evaluated` | Policy check | policy_type, result |
| `ai_classification` | AI call | model, input_type, output, confidence |

### 20.3 Sensitive Data Masking

Fields masked in logs: `password`, `token`, `secret`, `key`, `authorization`, `access_token`, `refresh_token`, `api_key`, `credentials`

---

## 21. Data Flow

### 21.1 Payment Recovery: End-to-End

```
1. TRIGGER
   Stripe → POST /integrations/webhooks/stripe
   │  Headers: stripe-signature
   │  Body: invoice.payment_failed event
   │
   ▼
   ┌──────────────────────────────────────┐
   │ verify_signature()                   │
   │ normalize_webhook() → CanonicalEvent │
   │   event_type: "payment_failed"       │
   │   entity_type: "invoice"             │
   │   entity_id: "in_123"                │
   └──────────────────────────────────────┘
    │
    ▼
   ┌──────────────────────────────────────┐
   │ dispatch_event()                     │
   │   is_duplicate() → check Redis       │
   │   route_event() → map to workflow    │
   └──────────────────────────────────────┘
    │
    ▼

2. WORKFLOW CREATION
   ┌──────────────────────────────────────┐
   │ _find_or_create_workflow()            │
   │   → Check guards:                    │
   │     - no active workflow exists      │
   │     - subscription active            │
   │     - invoice unpaid                 │
   │   → Create Workflow row              │
   │     workflow_type: payment_recovery  │
   │     current_state: DETECTED          │
   │     status: active                   │
   │     expiration_at: now + 7 days      │
   └──────────────────────────────────────┘
    │
    ▼

3. STATE: DETECTED
   ┌──────────────────────────────────────┐
   │ handle_event → _handle_detected()    │
   │   → transition(VALIDATING)           │
   │   → record timeline: workflow_created│
   └──────────────────────────────────────┘
    │
    ▼

4. STATE: VALIDATING
   ┌──────────────────────────────────────┐
   │ _handle_validating()                 │
   │   → Reload subscription (Recharge)   │
   │   → Reload invoice (Stripe)          │
   │   → Policy check: evaluate("retry")  │
   │   → If invalid → transition(FAILED)  │
   │   → If valid → transition(CLASSIFYING│
   │     _FAILURE)                        │
   └──────────────────────────────────────┘
    │
    ▼

5. STATE: CLASSIFYING_FAILURE
   ┌──────────────────────────────────────┐
   │ _handle_classifying_failure()        │
   │   → AI: classify_failure(reason)     │
   │   → Log AIInteraction                │
   │   → If blocked → transition(         │
   │     ESCALATED)                       │
   │   → If low confidence → transition(  │
   │     ESCALATED)                       │
   │   → If recoverable → transition(     │
   │     SELECTING_STRATEGY)              │
   └──────────────────────────────────────┘
    │
    ▼

6. STATE: SELECTING_STRATEGY
   ┌──────────────────────────────────────┐
   │ _handle_selecting_strategy()         │
   │   → Policy: evaluate("retry")        │
   │     → compute_retry_schedule()       │
   │   → Policy: evaluate("communication")│
   │     → allowed_channels, cadence      │
   │   → Decision: outreach or retry      │
   │     first?                           │
   │   → transition(OUTREACH_PENDING) or  │
   │     transition(RETRY_SCHEDULED)      │
   └──────────────────────────────────────┘
    │
    ▼

7. STATE: OUTREACH_PENDING → OUTREACH_SENT
   ┌──────────────────────────────────────┐
   │ _handle_outreach_pending()           │
   │   → AI: generate_email(context)      │
   │   → Check dedup: is_duplicate_comms()│
   │   → Send via channel (email/widget)  │
   │   → Record Communication row         │
   │   → transition(OUTREACH_SENT)        │
   │                                      │
   │ _handle_outreach_sent()              │
   │   → transition(WAITING_CUSTOMER)     │
   └──────────────────────────────────────┘
    │
    ▼

8. STATE: WAITING_CUSTOMER
   ┌──────────────────────────────────────┐
   │ Waiting for external events          │
   │ Possible triggers:                   │
   │                                      │
   │ payment_method_updated → RETRY_      │
   │   PENDING                            │
   │                                      │
   │ customer_frustrated → ESCALATED      │
   │   (AI: detect_frustration)           │
   │                                      │
   │ customer_cancel_requested →          │
   │   ESCALATED                          │
   │                                      │
   │ external_payment_success → RECOVERED │
   │                                      │
   │ timeout_elapsed (48h) → RETRY_       │
   │   SCHEDULED                          │
   └──────────────────────────────────────┘
    │
    ▼

9. STATE: RETRY_SCHEDULED → RETRY_PENDING
   ┌──────────────────────────────────────┐
   │ _handle_retry_scheduled()            │
   │   → schedule_job("retry_payment",    │
   │     execute_at)                      │
   │   → transition(RETRY_PENDING)        │
   │                                      │
   │ SchedulerWorker picks up job         │
   │                                      │
   │ _handle_retry_pending()              │
   │   → Reload invoice (Stripe)          │
   │   → Check retry limit not exceeded   │
   │   → transition(RETRYING)             │
   └──────────────────────────────────────┘
    │
    ▼

10. STATE: RETRYING → VERIFYING_RESULT
    ┌──────────────────────────────────────┐
    │ execute_action(retry_payment)        │
    │   → Guard: subscription active       │
    │   → Guard: invoice unpaid            │
    │   → Guard: retry limit OK            │
    │   → Idempotency check                │
    │   → Stripe: retry_payment(invoice)   │
    │   → Audit log                        │
    │   → transition(VERIFYING_RESULT)     │
    │                                      │
    │ _handle_verifying_result()           │
    │   → Reload invoice (Stripe)          │
    │   → If paid → transition(RECOVERED)  │
    │   → If failed, retries left →        │
    │     transition(WAITING_CUSTOMER)     │
    │   → If failed, no retries →          │
    │     transition(FAILED)               │
    │   → If state conflict → transition(  │
    │     PAUSED_RECONCILIATION)           │
    └──────────────────────────────────────┘
    │
    ▼

11. TERMINAL STATES
    ┌──────────────────────────────────────┐
    │ RECOVERED:                           │
    │   → Close workflow                   │
    │   → Release locks                    │
    │   → Update metrics                   │
    │   → Record timeline                  │
    │                                      │
    │ FAILED:                              │
    │   → Close workflow                   │
    │   → Record timeline                  │
    │   → (No further action)              │
    │                                      │
    │ ESCALATED:                           │
    │   → EscalationManager.create()       │
    │   → Pause workflow automation        │
    │   → Record timeline                  │
    │   → Notify merchant (future)         │
    │                                      │
    │ EXPIRED:                             │
    │   → Close workflow safely            │
    │   → Release locks                    │
    └──────────────────────────────────────┘
```

### 21.2 Customer Chat: End-to-End

```
Customer opens widget on store
    │
    ▼
widget.js loads → renders chat bubble
    │
    ▼
Customer types message → POST /widget/chat
{
  tenant_id: "...",
  user_id: "...",
  message: "What's my plan?",
  channel: "web_widget"
}
    │
    ▼
1. Rate limit check (20/min/IP)
2. Content moderation
3. Origin validation (check against allowed_origins)
    │
    ▼
4. Look up tenant from tenant_id
5. Log incoming ChatLog
6. RAG search: rag.search(tenant_id, message)
   → Embed query → Chroma query → dedup → threshold
    │
    ▼
7. Build system prompt:
   ┌──────────────────────────────────────────┐
   │ IF context found:                        │
   │ "Answer using ONLY the context below..." │
   │                                          │
   │ IF no context:                           │
   │ "You don't have this info. Offer to      │
   │ connect with specialist."                │
   └──────────────────────────────────────────┘
    │
    ▼
8. LLM: gpt-4o-mini
   - system prompt (from step 7)
   - user message
   - temperature: 0.3, max_tokens: 1000
    │
    ▼
9. Log response to ChatLog
10. Increment counters (unless test_widget)
11. Fire outgoing webhooks
    │
    ▼
Return: {response, latency_ms, escalated, resolution}
```

### 21.3 Webhook: End-to-End

```
Stripe → POST /integrations/webhooks/stripe
    │
    ▼
1. Read raw body
2. Extract stripe-signature header
3. Iterate connected Stripe connectors
4. Verify signature with each secret
5. Match → found tenant
6. stripe.events.normalize_webhook(payload)
   → CanonicalEvent {event_type: "payment_failed", ...}
    │
    ▼
7. dispatch_event(event)
   → is_duplicate() → Redis check
   → route_event(event) → workflow registry
   → PaymentRecoveryWorkflow.handle_event()
   → (continues to state machine flow above)
    │
    ▼
8. Return 200 OK immediately
   (processing continues asynchronously within the request)
```

---

## 22. Infrastructure Decisions & Rationale

### 22.1 Modular Monolith (Not Microservices)

| Decision | Rationale |
|----------|-----------|
| **Single codebase** | MVP team: 1-3 developers. Microservices = 10x ops overhead, 3x dev overhead |
| **Single deployable** | One Dockerfile, one `docker build`, one Railway service |
| **Internal module isolation** | `core/` never imports `channels/` or `admin/`. Enforced by import rules |
| **Worker processes** | Separate containers for background processing, same codebase |
| **Future extraction** | Bounded contexts mapped explicitly. If scale demands, extract `core/` as a service |

### 22.2 PostgreSQL (Primary Database)

| Decision | Rationale |
|----------|-----------|
| **Relational** | Workflows, customers, invoices — all relational data with strict consistency needs |
| **JSONB columns** | Flexible schemas (policies, event payloads) without separate NoSQL |
| **SQLAlchemy ORM** | Mature, well-understood, migration support via Alembic |
| **Managed by Railway** | Zero ops overhead |

### 22.3 ChromaDB (Vector Database)

| Decision | Rationale |
|----------|-----------|
| **Self-hosted** | No per-query costs, data stays within infrastructure |
| **Embeddable** | Persistent client mode for dev (no separate service) |
| **Simple API** | `add()`, `query()`, `delete()` — everything needed for MVP |
| **Cosmetic distance** | Works well with text-embedding-3-small |

**Trade-off acknowledged:** ChromaDB has less mature production operations than Pinecone/Weaviate. Acceptable for MVP. Future migration path: replace `rag/engine.py` with a different vector store adapter.

### 22.4 Redis (Cache, Queue, Locks)

| Decision | Rationale |
|----------|-----------|
| **Graceful degradation** | All Redis features have in-memory fallbacks. System works without Redis |
| **No Celery** | Celery adds complexity (broker, result backend, monitoring). Custom Redis scheduler is simpler for known job types |
| **Rate limiting** | Sliding window via Redis sorted sets. In-memory fallback for dev |

**Redis is optional.** Production benefits from it, but the system is fully functional without it (rate limits are less precise, scheduling is sync, dedup is process-local).

### 22.5 Auth Model (JWT + API Keys)

| Decision | Rationale |
|----------|-----------|
| **JWT over session DB** | Stateless, no DB lookup on every request, easy to verify |
| **Short-lived access tokens** | 15 min — limits damage from token leakage |
| **Refresh tokens** | 30 day — good UX (re-login once a month) |
| **API keys** | For server-to-server integration. HMAC-hashed, show-once |
| **Session cookies** | For admin UI. httponly prevents XSS token theft |

### 22.6 Storage (File System)

| Decision | Rationale |
|----------|-----------|
| **Local filesystem** | Simpler than S3 for MVP. Knowledge base files are small (50 MB/tenant) |
| **Structured by tenant** | `{knowledge_dir}/{tenant_id}/{file_id}/{filename}` |
| **Future S3 migration** | Swap storage backend when needed. Interface is already clean (`s3_key` field exists) |

### 22.7 No Message Broker

| Decision | Rationale |
|----------|-----------|
| **Webhooks processed inline** | Acceptable for MVP volumes (10s of events/day per tenant) |
| **No Kafka/RabbitMQ** | Would triple infrastructure complexity for no MVP benefit |
| **Future: event queue** | Add Redis-backed event queue when webhook volume exceeds request timeout |

---

## 23. Key Architectural Rules

### 23.1 Code Organization Rules

1. **Flat is better than nested** — but not flat at the expense of clarity. Max 3 levels deep.
2. **One module = one concern** — `admin.py` at 1150 lines must be split.
3. **Imports point inward** — `core/` never imports `channels/`, `admin/`, `knowledge/`.
4. **No circular imports** — enforced by the dependency graph above.

### 23.2 API Rules

1. **Every endpoint validates input** — Pydantic models or manual validation.
2. **Admin API returns JSON** — never HTML mixed with JSON.
3. **Errors return `{"detail": "..."}`** — with appropriate HTTP status.
4. **Webhook receivers return 200** — before processing completes.

### 23.3 Database Rules

1. **Every row has a tenant_id** — `UUID` type, indexed, foreign key to `tenants.id`.
2. **Timestamps are UTC** — naive datetimes stored as-is, interpreted as UTC.
3. **Soft deletes where needed** — `status='deleted'` not `DELETE FROM`.
4. **JSONB for flexible schemas** — not separate tables for every variation.

### 23.4 Workflow Rules

1. **AI never changes state** — workflows transition deterministically.
2. **Every transition is logged** — `workflow_transitions` + `timeline_events`.
3. **No duplicate active workflows** — lock per customer + workflow type.
4. **Source-of-truth revalidation** — before every action, reload from external system.
5. **Idempotency for all actions** — retries, messages, mutations, escalations.

### 23.5 Security Rules

1. **Credentials encrypted at rest** — Fernet symmetric encryption.
2. **API keys shown once** — never stored in plaintext, never returned.
3. **JWT secrets 32+ characters** — validated on startup.
4. **Session cookies httponly** — prevents XSS token theft.
5. **Widget origins validated** — CORS + origin allowlist per tenant.

---

*End of System Architecture Specification*
