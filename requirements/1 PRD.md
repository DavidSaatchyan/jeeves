# Jeeves — Product Requirements Document (MVP)

> **Version:** 1.0.0-mvp  
> **Status:** Draft  
> **Last updated:** 2026-05-11  

---

## Table of Contents

1. [Product Overview](#1-product-overview)
2. [System Architecture](#2-system-architecture)
3. [Features](#3-features)
4. [Domain Entities](#4-domain-entities)
5. [Workflow: PayGuard (Payment Recovery)](#5-workflow-payguard-payment-recovery)
6. [Permissions & Authentication](#6-permissions--authentication)
7. [User Flows](#7-user-flows)
8. [System Actions](#8-system-actions)
9. [Integrations](#9-integrations)
10. [MVP Scope & Limitations](#10-mvp-scope--limitations)
11. [Glossary](#11-glossary)

---

## 1. Product Overview

### 1.1 Vision

Jeeves is an AI agent platform for Shopify subscription brands (SMB). It connects to a merchant's business services (Shopify, Recharge, Stripe), ingests their knowledge base, and deploys autonomous AI agents that communicate with customers across channels to resolve issues and recover revenue — without requiring a support team.

### 1.2 Mission (MVP)

Deliver a single reliable agent — **PayGuard** — that recovers failed subscription payments automatically, safely, and deterministically, while keeping the merchant in full control via policy configuration.

### 1.3 Target Audience

- **Primary:** Shopify merchants using Recharge for subscriptions
- **Size:** SMB (1–50 employees, no dedicated support team)
- **Technical level:** Low-to-medium (can connect apps, configure settings)
- **Need:** Reduce churn from failed payments without hiring support staff

### 1.4 Core Principles

| Principle | Description |
|-----------|-------------|
| **Deterministic execution** | LLM never executes operational actions. It classifies, summarizes, and generates communication only. |
| **Idempotency** | All actions are retry-safe, deduplicated, and replay-safe. |
| **Merchant control** | Policies override AI suggestions. Merchant sets retry limits, escalation thresholds, communication cadence. |
| **State ownership** | Stripe = payment truth, Recharge = subscription truth, Shopify = customer/order truth. Conflicts trigger reconciliation. |
| **Auditability** | Every state transition, message, retry, escalation, and policy decision is logged. |
| **Safe escalation** | Automation stops when confidence is insufficient, frustration is detected, or ambiguity is unresolved. |

---

## 2. System Architecture

### 2.1 High-Level Architecture

```
┌──────────────┐     ┌─────────────────────────────────────────────┐
│  Merchant     │     │              Jeeves Platform                 │
│  (Shopify     │────▶│                                             │
│   store)      │     │  ┌─────────┐  ┌──────────┐  ┌───────────┐  │
│              │     │  │ Webhooks│─▶│  Event    │─▶│ Workflow  │  │
│              │     │  │ Ingest  │  │  Dispatcher│  │ Engine    │  │
│              │     │  └─────────┘  └──────────┘  └─────┬─────┘  │
│              │     │                                     │        │
│              │     │  ┌─────────┐  ┌──────────┐  ┌───────▼──────┐│
│              │     │  │ Policy  │  │  AI       │  │  Execution   ││
│              │     │  │ Engine  │  │  Classifier│  │  Dispatcher  ││
│              │     │  └─────────┘  └──────────┘  └───────┬──────┘│
│              │     │                                     │        │
│              │     │  ┌───────────────────────────────────▼──────┐│
│              │     │  │          Integrations Layer              ││
│              │     │  │  Shopify  │  Recharge  │  Stripe        ││
│              │     │  └──────────────────────────────────────────┘│
└──────────────┘     └─────────────────────────────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
              ┌─────▼─────┐           ┌───────▼──────┐
              │  Channels   │           │   Admin UI   │
              │            │           │              │
              │  • Widget   │           │  Dashboard   │
              │  • Email    │           │  Analytics   │
              │  • WhatsApp │           │  Config      │
              └────────────┘           └──────────────┘
```

### 2.2 Technology Stack

| Layer | Technology |
|-------|-----------|
| **API Framework** | FastAPI (Python 3.11+) |
| **Database** | PostgreSQL (SQLite for dev) |
| **ORM** | SQLAlchemy 2.0 |
| **Migrations** | Alembic |
| **AI / LLM** | OpenAI: gpt-4o-mini, text-embedding-3-small |
| **Vector Store** | ChromaDB (persistent / HTTP) |
| **Auth** | JWT (access + refresh tokens), bcrypt, API keys |
| **Caching / Scheduler** | Redis (with in-memory fallback) |
| **Frontend** | Jinja2 (SSR), vanilla JS, embedded widget (vanilla JS) |
| **Background Tasks** | FastAPI BackgroundTasks, Redis-based scheduler |
| **Containerization** | Docker |
| **Hosting** | Railway |

### 2.3 Core Modules

| Module | Responsibility |
|--------|---------------|
| `core/workflows/` | Workflow state machines, registry, runtime, scheduling |
| `core/ai/` | LLM classification, sentiment analysis, message generation |
| `core/events/` | Event schema, deduplication, dispatch |
| `core/execution/` | Idempotent action execution, audit logging |
| `core/commerce/` | Customer, subscription, invoice CRUD services |
| `core/communications/` | Multi-channel message sending, templates, dedup |
| `core/escalations/` | Escalation lifecycle, SLA tracking, assignment |
| `core/policies/` | Merchant policy evaluation (retry, escalation, communications) |
| `core/timeline/` | Audit trail recording and queries |
| `channels/` | Channel abstractions (widget, WhatsApp) |
| `integrations/` | Shopify, Recharge, Stripe API clients + webhook handlers |
| `rag.py` | RAG pipeline: chunking, embedding, Chroma search |
| `knowledge.py` | Knowledge base file management |

---

## 3. Features

### 3.1 Landing Page (`/`)

| ID | Feature | Description | MVP |
|----|---------|-------------|-----|
| F-1 | Public landing page | Product presentation, CTA to register | ✅ |
| F-2 | Legal pages | `/terms`, `/privacy` | ✅ |

### 3.2 Authentication (`/auth/*`)

| ID | Feature | Description | MVP |
|----|---------|-------------|-----|
| F-3 | Email/password registration | Password strength validation, auto-verify email | ✅ |
| F-4 | Email/password login | Bcrypt verification, session cookie | ✅ |
| F-5 | JWT token pair | Access token (15 min) + refresh token (30 days) | ✅ |
| F-6 | API key auth | `sk_` prefixed keys for server-to-server | ✅ |
| F-7 | Token revocation | Redis-based denylist | ✅ |
| F-8 | Google OAuth | Login/register via Google | ❌ |

### 3.3 Knowledge Base (`/admin/knowledge`)

| ID | Feature | Description | MVP |
|----|---------|-------------|-----|
| F-9 | File upload | Upload .txt, .pdf, .md files for RAG | ✅ |
| F-10 | Auto-indexing | Background chunking + embedding into Chroma | ✅ |
| F-11 | File list | View uploaded files, status, metadata | ✅ |
| F-12 | Single file delete | Remove file + its chunks from vector store | ✅ |
| F-13 | Clear all files | Remove all files + chunks | ✅ |
| F-14 | Upload progress | Per-file status indicator during processing | ✅ |
| F-15 | Stuck processing detection | Polling with 20 min timeout, status indicator | ✅ |
| F-16 | RAG chat test | Inline widget to test KB-driven answers | ✅ |
| F-17 | Duplicate detection | Content hash (SHA-256) prevents re-upload | ✅ |
| F-18 | Storage quota | 50 MB total per tenant | ✅ |
| F-19 | Orphan cleanup | Remove Chroma chunks with no DB record | ✅ |
| F-20 | Dedup cleanup | Remove duplicate chunks from Chroma | ✅ |
| F-21 | Section-aware chunking | Chunks prefixed with document section path | ✅ |

### 3.4 Connections (`/admin/connections`)

| ID | Feature | Description | MVP |
|----|---------|-------------|-----|
| F-22 | Connect Shopify | OAuth/API key, store credentials encrypted | ✅ |
| F-23 | Connect Recharge | API key, store credentials encrypted | ✅ |
| F-24 | Connect Stripe | API key, webhook secret | ✅ |
| F-25 | Disconnect provider | Remove credentials, deprovision tools | ✅ |
| F-26 | Test connection | Validate credentials with live API call | ✅ |
| F-27 | Connection status indicator | Show connected/disconnected/error per provider | ✅ |

### 3.5 Agents (`/admin/agents`)

| ID | Feature | Description | MVP |
|----|---------|-------------|-----|
| F-28 | Agent list | View available agents with status toggle | ✅ |
| F-29 | Agent enable/disable | Toggle agent on/off per merchant | ✅ |
| F-30 | Live feed | Real-time stream of transitions, communications, escalations | ✅ |
| F-31 | Funnel visualization | Pipeline breakdown: Detected → Classified → Outreach → Retry → Recovered | ✅ |
| F-32 | Queue management | View active workflows, escalations, log | ✅ |
| F-33 | Resolve escalation | Manually resolve an open escalation | ✅ |
| F-34 | Agent policy config | Per-agent policy settings (retry, communication, escalation thresholds) | ✅ |
| F-35 | Workflow detail | View workflow timeline and state history | ❌ |
| F-36 | Manual workflow trigger | Manually start a workflow for a customer | ❌ |

### 3.6 Channels (`/admin/channels`)

| ID | Feature | Description | MVP |
|----|---------|-------------|-----|
| F-37 | Channel list | View all configured channels with status | ✅ |
| F-38 | Web Widget config | Configure widget position, title, colors, allowed origins | ✅ |
| F-39 | Email config | Connect SendGrid/Resend API for outbound email | ✅ |
| F-40 | WhatsApp config | Connect WhatsApp Business API | ✅ |
| F-41 | Channel enable/disable | Toggle channel active/inactive | ✅ |
| F-42 | Credential masking | Mask secrets in UI (show dots) | ✅ |

### 3.7 Settings & Account (`/admin/settings`, `/admin/account`)

| ID | Feature | Description | MVP |
|----|---------|-------------|-----|
| F-43 | Workspace settings | Tenant name, email | ✅ |
| F-44 | API keys management | Create (show once), list, revoke | ✅ |
| F-45 | Notification prefs | Escalation alerts, approval alerts, workflow failure alerts, daily summary | ✅ |
| F-46 | Billing usage | Current plan, dialog count, overage charges, trial info | ✅ |
| F-47 | Account info | Plan, billing status, trial days left | ✅ |

### 3.8 Agent: PayGuard (Payment Recovery)

| ID | Feature | Description | MVP |
|----|---------|-------------|-----|
| F-48 | Payment failure detection | Webhook → canonical event → workflow creation | ✅ |
| F-49 | Failure classification | AI categorizes failure as recoverable / semi-recoverable / blocked | ✅ |
| F-50 | Retry scheduling | Deterministic retry schedule per policy | ✅ |
| F-51 | Customer outreach | Email + widget messages with templates | ✅ |
| F-52 | Retry execution | Idempotent Stripe payment retry | ✅ |
| F-53 | External payment detection | Detect if customer pays outside workflow | ✅ |
| F-54 | Frustration detection | AI sentiment analysis on customer messages | ✅ |
| F-55 | Escalation | Human handoff on ambiguity, frustration, policy conflict | ✅ |
| F-56 | Workflow expiration | 7-day timeout, safe termination | ✅ |
| F-57 | Reconciliation pause | Pause when Stripe/Recharge states conflict | ✅ |
| F-58 | Cancellation handling | Escalate if customer requests cancellation during recovery | ✅ |

**Not in MVP:** adaptive retry optimization, AI-generated discounts, dynamic negotiation, multi-subscription handling.

### 3.9 Customer Widget (`/widget/*`)

| ID | Feature | Description | MVP |
|----|---------|-------------|-----|
| F-59 | Embeddable widget JS | `<script>` tag injects chat bubble | ✅ |
| F-60 | Chat with RAG | Answers from merchant's knowledge base | ✅ |
| F-61 | Specialist fallback | "I don't know → connect with specialist" | ✅ |
| F-62 | Conversation rating | thumbs up/down + optional feedback | ✅ |
| F-63 | Inbox | Undelivered proactive messages | ✅ |
| F-64 | Origin validation | CORS + origin allowlist per tenant | ✅ |
| F-65 | Rate limiting | 20 messages/min per IP | ✅ |
| F-66 | Content moderation | OpenAI moderation + keyword filter | ✅ |

### 3.10 Analytics (`/admin/api/analytics`)

| ID | Feature | Description | MVP |
|----|---------|-------------|-----|
| F-67 | Revenue recovered | $ amount recovered in last 30 days | ✅ |
| F-68 | Save rate | % of recovered vs total failures | ✅ |
| F-69 | Churn prevented | Count of customers recovered | ✅ |
| F-70 | Workflow stats | Total / active / recovered / failed | ✅ |
| F-71 | Escalation count | Total escalations in period | ✅ |
| F-72 | Communications sent | Total outreach messages | ✅ |

---

## 4. Domain Entities

### 4.1 Entity Relationship Diagram (Conceptual)

```
Tenant
  ├── FileRecord          (uploaded KB files)
  ├── ChatLog             (chat history)
  ├── ConversationRating  (thumbs up/down)
  ├── WebhookConfig       (incoming/outgoing webhook settings)
  ├── ChannelConfig       (widget, email, whatsapp)
  ├── ApiKey              (server-to-server keys)
  ├── NotificationPreferences
  ├── PolicySet           (retry, communication, escalation, approval rules)
  ├── NativeConnector     (Shopify, Recharge, Stripe credentials)
  ├── Customer
  │     ├── Subscription
  │     │     └── Invoice
  │     │           └── PaymentFailure
  │     └── Workflow
  │           ├── WorkflowTransition
  │           ├── Communication
  │           ├── Escalation
  │           └── AIInteraction
  ├── CanonicalEvent      (ingested external events)
  └── TimelineEvent       (unified audit trail)
```

### 4.2 Entity Definitions

#### 4.2.1 Tenant

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| name | Text | Company/workspace name |
| email | Text | Login email (unique) |
| hashed_password | Text | bcrypt hash |
| email_verified | Bool | Auto-verified in MVP |
| trial_ends | DateTime | 14-day trial |
| is_active | Bool | Account active flag |
| dialogs_used | Int | Counter for billing |
| resolved_count | Int | Counter for billing |
| created_at | DateTime | |

**States:** `active`, `trial_expired`, `disabled`

#### 4.2.2 FileRecord

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| tenant_id | UUID FK | Owner |
| filename | Text | Original filename |
| s3_key | Text | Local storage path (MVP) |
| status | String | `processing` / `ready` / `failed` |
| content_hash | String | SHA-256 for dedup |
| chunks_total | Int | Number of Chroma chunks |
| size_bytes | Int | File size |
| error | Text | Error message if failed |
| created_at | DateTime | |

**States:** `processing` → `ready` | `failed`

#### 4.2.3 ChatLog

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| tenant_id | UUID FK | Owner |
| user_id | Text | End customer identifier |
| direction | String | `incoming` / `outgoing` |
| message | Text | Incoming message |
| response | Text | AI response |
| resolution | String | `resolved` / `escalated` |
| action_called | Text | Action taken by agent |
| latency_ms | Int | Response time |
| delivered | Bool | Proactive message delivered |
| sources | JSONB | RAG retrieval trace |
| session_id | UUID | Conversation grouping |
| extra_fields | JSONB | Widget identify() data |
| channel | String | `web_widget`, `whatsapp`, `rest_api` |
| created_at | DateTime | |

#### 4.2.4 Customer

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| tenant_id | UUID FK | Owner |
| email | Text | |
| phone | Text | |
| shopify_customer_id | Text | Shopify ID |
| stripe_customer_id | Text | Stripe ID |
| recharge_customer_id | Text | Recharge ID |
| first_seen_at | DateTime | |
| last_seen_at | DateTime | |
| risk_level | String | |
| sentiment_state | String | |
| frustration_score | Int | |
| created_at | DateTime | |
| updated_at | DateTime | |

#### 4.2.5 Subscription

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| tenant_id | UUID FK | |
| customer_id | UUID FK | |
| external_subscription_id | Text | Recharge ID |
| status | String | `active`, `paused`, `cancelled`, etc. |
| plan_name | Text | |
| product_sku | Text | |
| renewal_date | DateTime | |
| started_at | DateTime | |
| pause_state | String | |
| skip_state | String | |
| mrr | Int | Monthly recurring revenue (cents) |
| currency | String | |
| created_at | DateTime | |
| updated_at | DateTime | |

**States:** `active`, `paused`, `cancelled`, `expired`, `past_due`

#### 4.2.6 Invoice

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| tenant_id | UUID FK | |
| customer_id | UUID FK | |
| subscription_id | UUID FK | |
| external_invoice_id | Text | Stripe ID |
| status | String | `open`, `paid`, `unpaid`, `void` |
| amount_due | Int | Cents |
| currency | String | |
| payment_attempt_count | Int | |
| last_failure_reason | Text | |
| due_date | DateTime | |
| paid_at | DateTime | |
| created_at | DateTime | |
| updated_at | DateTime | |

**States:** `open` → `paid` | `unpaid` | `void`

#### 4.2.7 Workflow

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| tenant_id | UUID FK | |
| customer_id | Text | |
| workflow_type | String | `payment_recovery` |
| current_state | String | Current FSM state |
| status | String | `active`, `paused`, `completed`, `escalated` |
| started_at | DateTime | |
| updated_at | DateTime | |
| completed_at | DateTime | |
| priority | Int | |
| expiration_at | DateTime | 7-day default |
| locked_until | DateTime | Concurrent mutation guard |
| escalation_state | String | |

**States:** `active` | `paused` | `completed` | `escalated`

#### 4.2.8 WorkflowTransition

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| workflow_id | UUID FK | |
| from_state | String | |
| to_state | String | |
| trigger_event | Text | |
| decision_reason | Text | Why transition happened |
| policy_snapshot | JSONB | Policies at time of transition |
| performed_by | Text | `system`, `admin`, `escalation` |
| created_at | DateTime | |

#### 4.2.9 Communication

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| workflow_id | UUID FK | |
| customer_id | UUID FK | |
| tenant_id | UUID FK | |
| channel | String | `email`, `widget` |
| direction | String | `outbound` |
| message_type | String | `payment_update`, `retry_reminder`, etc. |
| template_name | String | |
| delivery_status | String | `pending`, `sent`, `delivered`, `failed` |
| deduplication_key | Text | |
| sent_at | DateTime | |
| delivered_at | DateTime | |
| created_at | DateTime | |

**States:** `pending` → `sent` → `delivered` | `failed`

#### 4.2.10 Escalation

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| workflow_id | UUID FK | |
| customer_id | UUID FK | |
| tenant_id | UUID FK | |
| escalation_reason | Text | |
| severity | String | `low`, `medium`, `high`, `critical` |
| owner_id | Text | |
| assigned_to | Text | |
| source | String | `system`, `admin`, `customer` |
| extra_metadata | JSONB | |
| sla_breached | Bool | |
| status | String | `OPEN`, `ASSIGNED`, `IN_PROGRESS`, `WAITING_EXTERNAL`, `RESOLVED`, `CLOSED` |
| created_at | DateTime | |
| resolved_at | DateTime | |
| updated_at | DateTime | |

**States:** `OPEN` → `ASSIGNED` → `IN_PROGRESS` ⇄ `WAITING_EXTERNAL` → `RESOLVED` → `CLOSED`

#### 4.2.11 PolicySet

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| tenant_id | UUID FK (unique) | |
| retry_policy | JSONB | `{max_attempts, retry_windows, cooldown}` |
| communication_policy | JSONB | `{max_outreach, cooldown, allowed_channels}` |
| escalation_policy | JSONB | `{frustration_threshold, sla_hours}` |
| approval_policy | JSONB | `{requires_approval, allowed_save_actions}` |
| enabled_workflows | JSONB | `["payment_recovery"]` |
| created_at | DateTime | |
| updated_at | DateTime | |

#### 4.2.12 ChannelConfig

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| tenant_id | UUID FK | |
| channel_type | String | `web_widget`, `whatsapp`, `email` |
| config | JSONB | Channel-specific settings (credentials, styling) |
| status | String | `active`, `inactive`, `error` |
| last_error | Text | |
| created_at | DateTime | |
| updated_at | DateTime | |

**States:** `active` | `inactive` | `error`

#### 4.2.13 NativeConnector

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| tenant_id | UUID FK | |
| provider | String | `shopify`, `recharge`, `stripe` |
| status | String | `connected`, `error` |
| credentials | Text | Fernet-encrypted JSON |
| meta | JSONB | Provider-specific metadata |
| created_at | DateTime | |
| updated_at | DateTime | |

#### 4.2.14 CanonicalEvent

| Field | Type | Description |
|-------|------|-------------|
| id | UUID | Primary key |
| tenant_id | UUID FK | |
| event_type | String | `payment_failed`, `invoice_payment_failed`, `rebill_failed` (20 types) |
| event_source | String | `stripe`, `shopify`, `recharge` |
| entity_type | String | `invoice`, `subscription`, `customer` |
| entity_id | Text | External entity ID |
| payload | JSONB | Raw event data |
| occurred_at | DateTime | |
| created_at | DateTime | |

---

## 5. Workflow: PayGuard (Payment Recovery)

### 5.1 Trigger Events

- `payment_failed` (Stripe)
- `invoice_payment_failed` (Stripe)
- `rebill_failed` (Recharge)

### 5.2 Preconditions

All must be true before workflow activates:

1. Subscription status is `active`
2. Invoice status is `open` or `unpaid`
3. No successful payment already recorded for this invoice
4. No active `payment_recovery` workflow exists for this customer+subscription
5. Customer is not already escalated
6. Merchant policy allows automated recovery
7. Retry eligibility is valid

### 5.3 State Machine

```
                        ┌──────────────┐
                        │   DETECTED   │
                        └──────┬───────┘
                               │
                        ┌──────▼───────┐
                        │  VALIDATING  │◄──────────────┐
                        └──────┬───────┘               │
                      ┌───────┼───────┐                │
                      ▼       ▼       ▼                │
                 ┌────────┐ ┌──────────────┐          │
                 │ FAILED │ │CLASSIFYING   │          │
                 └────────┘ │  FAILURE     │          │
                            └──────┬───────┘          │
                              ┌────┴────┐             │
                              ▼         ▼             │
                     ┌─────────────────┐   ┌────────┐│
                     │SELECTING_STRATEGY│   │ESCALATED││
                     └──────┬──────────┘   └────────┘│
                    ┌───────┼───────┐                 │
                    ▼       ▼       ▼                 │
              ┌──────────┐ ┌──────────────┐          │
              │OUTREACH  │ │RETRY         │          │
              │ PENDING  │ │ SCHEDULED    │          │
              └────┬─────┘ └──────┬───────┘          │
                   ▼              ▼                   │
              ┌──────────┐ ┌──────────────┐          │
              │OUTREACH  │ │RETRY         │          │
              │  SENT    │ │ PENDING      │          │
              └────┬─────┘ └──────┬───────┘          │
                   ▼              ▼                   │
              ┌──────────┐ ┌──────────────┐          │
              │ WAITING  │ │  RETRYING    │          │
              │ CUSTOMER │ └──────┬───────┘          │
              └────┬─────┘       ▼                   │
              ┌────┴────┐  ┌──────────────┐          │
              ▼         ▼  │  VERIFYING   │          │
         ┌────────┐ ┌────┐ │   RESULT     │          │
         │RETRY   │ │RECOV│ └──┬───┬───┬───┘          │
         │SCHEDUL │ │ERED │    │   │   │              │
         └────────┘ └─────┘    │   │   │              │
          (to RETRY_PENDING)  ▼   ▼   ▼               │
                         ┌────┐ ┌──────────┐ ┌──────┐ │
                         │REC │ │ WAITING  │ │PAUSED│──┘
                         │OVER│ │ CUSTOMER │ │RECON │
                         │ED  │ └──────────┘ │CILIA │
                         └────┘              │TION  │
                                             └──────┘

Terminal:  RECOVERED, FAILED, ESCALATED, EXPIRED
Loop-back: PAUSED_RECONCILIATION → VALIDATING
```

### 5.4 State Handlers

| State | AI Allowed | Action |
|-------|-----------|--------|
| **DETECTED** | No | Create workflow, lock duplicates, persist snapshot |
| **VALIDATING** | No | Validate subscription active, invoice unpaid, policy allows. → FAILED if invalid |
| **CLASSIFYING_FAILURE** | Yes | Classify as recoverable / semi-recoverable / blocked. → ESCALATED if blocked |
| **SELECTING_STRATEGY** | No | Deterministic: compute retry schedule, communication plan, escalation threshold |
| **OUTREACH_PENDING** | Yes | Generate communication content (email/widget). Validate cadence, dedup |
| **OUTREACH_SENT** | No | Persist delivery status, idempotency key |
| **WAITING_CUSTOMER** | Yes | Handle events: payment updated → retry, frustrated → escalate, cancel → escalate, timeout → retry schedule |
| **RETRY_SCHEDULED** | No | Enqueue retry job in Redis, persist window |
| **RETRY_PENDING** | No | Reload Stripe state, validate retry limit, check external payment |
| **RETRYING** | No | Execute Stripe charge, log result with idempotency key |
| **VERIFYING_RESULT** | No | Reload authoritative Stripe invoice state → route accordingly |
| **PAUSED_RECONCILIATION** | No | Source-of-truth conflict. Re-validate and continue or escalate |
| **RECOVERED** | No | Close workflow, release locks, update metrics |
| **FAILED** | No | Terminal. Retry limit / ineligible / timeout |
| **ESCALATED** | No | Terminal for automation. Human ownership begins |
| **EXPIRED** | No | Terminal. Workflow exceeded 7-day window |

### 5.5 Retry Logic

- **Max attempts:** 3 (configurable per policy)
- **Windows:** 5 min, 1 hour, 24 hours (default)
- **Cooldown between attempts:** 5 minutes
- **Before each retry:** re-validate source of truth (Stripe)
- **Idempotency:** idempotency_key per retry

### 5.6 Communication Templates (MVP)

| Template | Purpose | Channel |
|----------|---------|---------|
| `payment_update` | "Your payment failed, please update" | Email, Widget |
| `retry_reminder` | "We'll retry on {date}" | Email |
| `auth_assistance` | "3DS authentication needed" | Email |
| `save_offer` | "Before you go, here's an option" | Email, Widget |

### 5.7 Escalation Triggers

| Condition | Action |
|-----------|--------|
| Failure classified as `blocked` | → ESCALATED |
| AI confidence < threshold | → ESCALATED |
| Customer frustration level ≥ `medium` | → ESCALATED |
| Customer explicitly requests cancellation | → ESCALATED |
| Retry limit exceeded | → FAILED |
| Stripe/Recharge state conflict | → PAUSED_RECONCILIATION |
| Workflow inactive > 7 days | → EXPIRED |
| Manual admin escalation | → ESCALATED |

---

## 6. Permissions & Authentication

### 6.1 Authentication Methods

| Method | Where Used | MVP |
|--------|-----------|-----|
| JWT access token (Bearer) | API endpoints | ✅ |
| JWT refresh token | `/auth/refresh` | ✅ |
| Session cookie | Admin UI pages | ✅ |
| API key (`sk_*`) | Server-to-server | ✅ |

### 6.2 Roles (MVP)

| Role | Access | MVP |
|------|--------|-----|
| **Owner** | Full access to all admin pages, settings, billing | ✅ |
| **Admin** | Full access to all admin pages except billing | ❌ |
| **Agent** | Read-only: agents dashboard, analytics | ❌ |
| **API** | Programmatic access via API key | ✅ |

**MVP simplification:** Only `Owner` role exists. All authenticated users are owners of their tenant.

### 6.3 Rate Limits

| Endpoint | Limit | Scope |
|----------|-------|-------|
| `/auth/register` | 3/hour | IP |
| `/auth/login` | 5/min | IP |
| `/chat` | 20/min | IP |
| `/widget/chat` | 20/min | IP |

---

## 7. User Flows

### 7.1 Onboarding Flow

```
Landing Page
    │
    ▼
Register (/auth/register)
    │
    ▼
Auto-login → Admin Panel (/admin/agents)
    │
    ├──▶ 1. Connect services (/admin/connections)
    │        ├── Shopify
    │        ├── Recharge
    │        └── Stripe
    │
    ├──▶ 2. Upload knowledge base (/admin/knowledge)
    │        └── Add product/FAQ/policy docs
    │
    ├──▶ 3. Configure PayGuard agent (/admin/agents)
    │        ├── Enable agent
    │        ├── Set retry/comms/escalation policies
    │        └── Review analytics
    │
    └──▶ 4. Set up channels (/admin/channels)
             ├── Embed widget on store
             ├── Connect email (SendGrid/Resend)
             └── Connect WhatsApp
```

### 7.2 Payment Recovery Flow (System)

```
1. Stripe emits invoice.payment_failed webhook
    │
    ▼
2. Jeeves receives → normalizes → CanonicalEvent
    │
    ▼
3. Dispatch → route_event → find_or_create Workflow
    │
    ▼
4. Workflow: DETECTED → VALIDATING
    │  └── Validate subscription active, invoice unpaid, no duplicate
    │
    ▼
5. Workflow: CLASSIFYING_FAILURE
    │  └── AI classifies failure (recoverable/semi/blocked)
    │
    ▼
6. Workflow: SELECTING_STRATEGY
    │  └── Policy engine computes retry schedule + communication plan
    │
    ▼
7. Workflow: OUTREACH_PENDING → OUTREACH_SENT → WAITING_CUSTOMER
    │  └── Send email/widget message to customer
    │
    ▼
8. ┌── Customer updates card → RETRY_PENDING → RETRYING → VERIFYING
    ├── Customer ignores → timeout → RETRY_SCHEDULED → RETRY_PENDING
    ├── Customer frustrated → ESCALATED
    └── Customer cancels → ESCALATED
    │
    ▼
9. VERIFYING_RESULT:
    ├── Paid → RECOVERED
    ├── Still failed, retries left → WAITING_CUSTOMER
    ├── Retry limit → FAILED
    └── State conflict → PAUSED_RECONCILIATION
```

### 7.3 Customer Widget Chat Flow

```
Customer opens widget on store
    │
    ▼
Widget loads → POST /widget/chat {tenant_id, user_id, message}
    │
    ▼
1. Rate limit check
2. Content moderation
3. Origin validation
    │
    ▼
4. RAG search (tenant's knowledge base)
    ├── Context found → build system prompt with context
    └── No context → "I don't know" fallback
    │
    ▼
5. LLM call (gpt-4o-mini) with system prompt + message
    │
    ▼
6. Log to ChatLog, increment counters
    │
    ▼
7. Return response to widget
```

### 7.4 Admin Dashboard Flow

```
Admin logs in → /admin/agents
    │
    ▼
Dashboard shows:
├── Analytics: revenue recovered, save rate, churn prevented
├── Feed: real-time transitions, communications, escalations
├── Funnel: Detected → Classified → Outreach → Retry → Recovered
├── Queue: active workflows, escalations, log
│
├── Agent toggle + policy config
│
▼
Drill down:
├── Click workflow → timeline (MVP: via API, UI TBD)
└── Click escalation → resolve modal
```

---

## 8. System Actions

All system actions are deterministic (non-AI), idempotent, and audited.

### 8.1 Workflow Operations

| Action | Description | Idempotent |
|--------|-------------|------------|
| `create_workflow` | Create workflow instance, lock context | ✅ (by lock) |
| `transition_workflow` | Execute state transition, validate, persist | ✅ (by idempotency key) |
| `pause_workflow` | Pause automation, release escalation | ✅ |
| `resume_workflow` | Resume paused workflow | ✅ |
| `expire_workflow` | Terminate expired workflow safely | ✅ |
| `escalate_workflow` | Create escalation, pause workflow | ✅ |

### 8.2 Commerce Operations

| Action | Description | Idempotent |
|--------|-------------|------------|
| `upsert_customer` | Create or update customer record | ✅ (by external ID) |
| `upsert_subscription` | Sync subscription from Recharge | ✅ (by external ID) |
| `upsert_invoice` | Sync invoice from Stripe | ✅ (by external ID) |
| `record_payment_failure` | Log payment failure for audit | ✅ |
| `execute_retry_payment` | Charge customer via Stripe | ✅ (by idempotency key) |

### 8.3 Communication Operations

| Action | Description | Idempotent |
|--------|-------------|------------|
| `send_email` | Send via SendGrid/Resend | ✅ (by communication_id) |
| `queue_widget_message` | Queue message for widget inbox | ✅ (by communication_id) |
| `generate_email_content` | AI: compose email subject + body | ❌ (stateless) |
| `generate_widget_message` | AI: compose short widget message | ❌ (stateless) |

### 8.4 Policy Operations

| Action | Description |
|--------|-------------|
| `evaluate_retry_policy` | Compute retry schedule from policy + context |
| `evaluate_communication_policy` | Check outreach limit, cooldown, allowed channels |
| `evaluate_escalation_policy` | Check frustration threshold, failure count |
| `evaluate_approval_policy` | Check if action requires approval |

### 8.5 Escalation Operations

| Action | Description | Idempotent |
|--------|-------------|------------|
| `create_escalation` | Open new escalation | ✅ (by workflow_id) |
| `assign_escalation` | Assign to operator (round-robin) | ✅ |
| `resolve_escalation` | Mark resolved, log reason | ✅ |
| `check_sla_breaches` | Find escalations past SLA | ✅ (read-only) |

### 8.6 AI Operations (Non-deterministic)

| Action | Input | Output |
|--------|-------|--------|
| `classify_failure` | Payment failure reason + code | `{category, confidence, explanation}` |
| `detect_frustration` | Customer message | `{level, confidence, indicators}` |
| `generate_email` | Context + template name | `{subject, body}` |
| `generate_widget_message` | Context + template name | `{message}` |

---

## 9. Integrations

### 9.1 Shopify

| Capability | MVP |
|-----------|-----|
| Customer data retrieval | ✅ |
| Order data retrieval | ✅ |
| Webhook: order creation, fulfillment | ✅ |
| Write-back: customer notes, tags | ❌ (future) |

### 9.2 Recharge

| Capability | MVP |
|-----------|-----|
| Subscription retrieval | ✅ |
| Subscription mutation: pause, skip, delay | ✅ |
| Webhook: rebill failed, charge processed | ✅ |
| Customer retrieval | ✅ |

### 9.3 Stripe

| Capability | MVP |
|-----------|-----|
| Invoice retrieval | ✅ |
| Payment retry (charge) | ✅ |
| Webhook: invoice.payment_failed, invoice.paid | ✅ |
| Payment method status check | ✅ |
| Refunds | ❌ (future) |

### 9.4 Webhook (General)

| Capability | MVP |
|-----------|-----|
| Incoming webhook (context provider) | ✅ |
| Outgoing webhook (event notification) | ✅ |
| HMAC-SHA256 signature verification | ✅ |
| Field mapping (incoming → agent context) | ✅ |

---

## 10. MVP Scope & Limitations

### 10.1 In Scope

- **1 agent:** PayGuard (payment recovery)
- **3 integrations:** Shopify (read customer), Recharge (read subscription), Stripe (read invoice, execute retry)
- **3 channels:** Web Widget, Email (SendGrid/Resend), WhatsApp
- **1 communication direction:** Outbound (inbound via widget)
- **Knowledge base:** Upload txt/pdf/md, RAG, no segment-specific retrieval
- **Admin UI:** Agents dashboard, connections, knowledge, channels, settings, account
- **Billing:** Metered (per resolved dialog), free trial, no payment collection (MVP)

### 10.2 Explicitly Out of Scope (MVP)

| Area | What's excluded |
|------|----------------|
| **Agents** | Cancellation Save, WISMO, any future agent |
| **Integrations** | WooCommerce, BigCommerce, custom API |
| **Channels** | Telegram, Instagram, SMS, Messenger |
| **Payments** | Refunds, partial refunds, discounts, coupons |
| **Advanced AI** | Adaptive retry optimization, churn prediction, dynamic negotiation, AI-generated incentives |
| **Multi-workflow** | Cross-workflow coordination, dependency handling |
| **Multi-subscription** | Bundle subscriptions, multi-SKU dependency |
| **Collaboration** | Team accounts, role-based access, operator assignment |
| **Onboarding** | Guided setup wizard, onboarding checklist |
| **Reporting** | Custom date ranges, export, scheduled reports |
| **Automation** | Proactive campaigns, scheduled outreach, batch operations |
| **Compliance** | GDPR data export/deletion, SOC2 audit log |
| **Infrastructure** | Multi-region, read replicas, CDN |

### 10.3 Known Technical Debt

| Area | Issue | Priority |
|------|-------|----------|
| **State machine** | Inline state handler logic in `PaymentRecoveryWorkflow` — should use pluggable handler registry | Medium |
| **Policy engine** | Default policies hardcoded, need proper validation + versioning | Low |
| **Channels** | WhatsApp channel has REST API endpoints but no full state machine integration | Low |
| **Tests** | All test files removed in MVP cleanup; no test coverage | High |
| **Config** | `config.yaml` is gitignored, `top_k: 15` must be set manually on deploy | Low |
| **Cancellation save** | Source `.py` files for `commerce/shipment.py` and `commerce/risk.py` are missing (only `.pyc` exists) | Low |

---

## 11. Glossary

| Term | Definition |
|------|------------|
| **Agent** | Autonomous workflow executor that handles a specific business scenario (e.g., PayGuard). |
| **Canonical Event** | Normalized external event with standardized schema, used to trigger workflows. |
| **Channel** | Communication medium through which Jeeves interacts with end customers. |
| **Chunk** | A segment of text from a knowledge base document, embedded and stored in the vector DB. |
| **Deterministic** | Operation whose outcome is fully defined by its inputs (no AI variability). |
| **Escalation** | Transfer of a workflow from automation to human ownership. |
| **Idempotency** | Property where an operation produces the same result regardless of how many times it's executed. |
| **Knowledge Base** | Collection of documents uploaded by a merchant that the AI uses to answer customer questions. |
| **PayGuard** | The payment recovery agent. |
| **Policy** | Merchant-configurable rules that govern agent behavior (retry limits, communication cadence, etc.). |
| **RAG** | Retrieval-Augmented Generation — search chunks → LLM answers with context. |
| **Recoverable** | A payment failure type that can potentially be resolved through retry or customer action. |
| **Semi-recoverable** | A failure type that requires customer intervention (e.g., expired card). |
| **Tenant** | A single merchant account in the Jeeves platform. |
| **Workflow** | A state machine instance that tracks a specific business process for a specific customer. |
| **Workflow Type** | The class of workflow (e.g., `payment_recovery`, `cancellation_save`). |

---

*End of PRD*
