# Jeeves MVP — Scope Analysis

## 1. Product Audit (Current State)

### 1.1 What's Built (Production-Ready)

| Area | Status | Details |
|------|--------|---------|
| **Widget** | ✅ | Web Component (`<jeeves-widget>`), Shadow DOM, localStorage, configurable, auto-detects API origin |
| **Widget Chat** | ✅ | POST `/widget/chat` — intent classification → WISMO / RAG / general LLM |
| **Admin Panel** | ✅ | 11 SSR pages: agents, inbox, knowledge, connections, settings, channels, account, analytics, logs |
| **Auth** | ✅ | JWT cookie-based, register/login/logout, refresh tokens, API keys |
| **Inbox** | ✅ | 20+ routes, SSE streaming, canned responses, customer profile, assign/takeover/close/return-to-AI |
| **WISMO Workflow** | ✅ | Order tracking state machine: inquiry → identify → fetch → classify → notify → resolve/escalate |
| **RAG** | ✅ | ChromaDB vector store, file upload, product catalog indexing, search |
| **WhatsApp Channel** | ✅ | Webhook handler, message send, verify token |
| **Shopify Integration** | ✅ | Order/fulfillment fetch, webhooks, native connector |
| **Policies** | ✅ | PolicyEngine with configurable rules per workflow type |
| **Dual-Write** | ✅ | All chat paths write to Conversation + Message tables (and ChatLog for backward compat) |

### 1.2 What's Partial (Needs Work)

| Area | Status | Gap |
|------|--------|-----|
| **Tests** | ⚠️ 322 tests, but only RAG/chunking/catalog/WISMO covered | No tests for admin routes, auth, inbox, workflows runtime, events, policies, commerce, communications, channels/widget, shared modules |
| **Email Channel** | ⚠️ SendGrid/Resend configured in `core/communications/` | No dedicated email channel adapter (inbound email webhook). Only outbound via `send_communication()` |
| **Stripe Integration** | ⚠️ Model exists (`stripe_customer_id`, `Invoices`) | No actual Stripe API integration. `_has_payment()` always returns False. Billing is entirely stub |
| **Recharge Integration** | ⚠️ Model exists (`recharge_customer_id`, `Subscription`) | No actual Recharge API connection |
| **Config YAML** | ⚠️ `config.yaml` with `top_k:15`, AI model settings | Must be manually created on each deploy — no seeding/defaults |
| **Rate Limiting** | ⚠️ In-memory fallback for all Redis features | Not suitable for multi-instance Railway deployment |
| **Monitoring** | ⚠️ Request logging middleware only | No metrics, no Sentry/OpenTelemetry, no alerting |

### 1.3 What's Missing (Not Built)

| Area | Priority | Why It Matters |
|------|----------|----------------|
| **PayGuard Workflow** | High | Payment recovery is the second most common support query after WISMO. Referenced in funnel code but not implemented. Without it, Jeeves can only handle "where is my order" |
| **General Support Workflow** | High | Currently only WISMO has a dedicated workflow. All other intents (billing, account, product questions) fall through to simple LLM response with no state machine, no action execution, no escalation |
| **Email Channel (inbound)** | High | Customers need to email support@... and have it appear in the inbox. Currently only outbound (proactive notifications). Email is 30-40% of support volume for most companies |
| **Widget Unread Badge** | Medium | `/widget/inbox` marks ALL messages delivered on every poll, even unread ones. Need proper unread tracking or at least a badge counter |
| **Agent/Operator Model** | Medium | Currently operator identity = tenant email. No roles, no team management, no agent status (online/away). Fine for MVP but limits growth |
| **CSAT Survey** | Low | Post-conversation rating is already implemented (`POST /widget/rating`) but not automatically triggered after close |
| **Audit Log for Admin** | Low | No tracking of which operator did what in the admin panel |
| **SSE → WebSocket** | Low | SSE polling works, WebSocket would be lower latency |

---

## 2. Competitive Analysis

### 2.1 Market Positioning

```
                    COMPREHENSIVE SUITE
                    ┌─────────────────────────────────────────────┐
                    │  Zendesk AI      Intercom Fin               │
                    │  Freshdesk Freddy LivePerson                │
                    │  Ada             Forethought                │
                    └─────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴────────────────┐
                    │         JEEVES                  │
                    │   (AI-first, workflow-native,   │
                    │    single-tenant focused)       │
                    └────────────────────────────────┘
                                    │
                    ┌───────────────┴────────────────┐
                    │  Crisp           Tidio          │
                    │  Chatbase        ManyChat       │
                    └─────────────────────────────────┘
                    SMB / NICHE
```

### 2.2 Feature Comparison

| Feature | Jeeves | Crisp | Tidio | Intercom | Zendesk | Chatbase |
|---------|--------|-------|-------|----------|---------|----------|
| **AI Chat Widget** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **RAG Knowledge Base** | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ |
| **Workflow State Machine** | ✅ WISMO | ❌ | ❌ | ✅ Fin Tasks | ✅ Agent Builder | ❌ |
| **Operator Inbox** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Customer Profile** | ✅ | ✅ | ❌ | ✅ | ✅ | ❌ |
| **Canned Responses** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **WhatsApp** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Email (inbound)** | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Multi-Workflow** | ❌ (only WISMO) | ❌ | ❌ | ✅ | ✅ | ❌ |
| **Stripe Integration** | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| **Shopify Integration** | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ |
| **Team/Agent Management** | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **SSE/Real-time** | ✅ SSE | ✅ WebSocket | ✅ SSE | ✅ WebSocket | ✅ WebSocket | ❌ polling |
| **Mobile SDK** | ❌ | ✅ | ❌ | ✅ | ✅ | ❌ |
| **Self-Hosted Option** | ✅ (open source) | ❌ | ❌ | ❌ | ❌ | ❌ |

### 2.3 Jeeves' Unique Advantages

1. **Open source / self-hosted** — No vendor lock-in, no per-ticket pricing. This is the #1 reason companies build vs buy
2. **Workflow-native architecture** — WISMO shows what's possible: a real state machine with order lookups, fulfillment checks, policy-based escalation. Intercom Fin and Crisp Hugo are "Q&A only" — they cannot autonomously check order status or trigger refunds
3. **Unified conversation + workflow** — Operator sees workflow state (order delayed, auto-escalated) directly in the inbox. Crisp/Intercom show chat history only
4. **Shopify-native** — Deep Shopify integration with order/fulfillment fetching
5. **No per-resolution pricing** — Flat infrastructure cost regardless of AI success rate

### 2.4 Jeeves' Critical Gaps vs Market

1. **Only 1 workflow type (WISMO)** — Competitors handle billing, account, product, technical support. Jeeves falls back to stateless LLM for everything non-WISMO
2. **No inbound email** — 30-40% of support volume. Customers expect to email `support@store.com`
3. **No PayGuard** — Payment failures are the #2 support driver. Without it, Jeeves solves only order-tracking use case
4. **No agent team management** — Single operator identity (tenant email). No "assign to Alice", no statuses
5. **No proper mobile SDK** — Widget works in mobile browser but no native SDK

---

## 3. MVP Scope Definition

### 3.1 Guiding Principles

- **Launch with one clear use case done well** (order tracking + general Q&A) rather than 5 broken ones
- **Flat pricing** ($0/resolution) is our competitive moat — never introduce per-resolution pricing
- **Workflow-native** is our differentiator — every new use case gets a state machine, not a prompt
- **Self-service onboarding** — tenant should go from signup to embedded widget in <5 minutes
- **Three-channel launch**: Web widget + WhatsApp + Email (inbound)

### 3.2 MVP Must-Have (Ship-blocking)

| # | Item | Effort | Why |
|---|------|--------|-----|
| 1 | **PayGuard Workflow** | 2-3 weeks | #2 support query after WISMO. Payment recovery with retry logic, dunning, escalation. Without it, Jeeves is "just an order tracker" |
| 2 | **Inbound Email Channel** | 1-2 weeks | Parse incoming emails via SendGrid inbound parse webhook → create Conversation + Message. Without it, customers can't email support |
| 3 | **General Support Workflow** | 2-3 weeks | Catch-all workflow for non-WISMO, non-PayGuard intents: product questions, account issues, returns. Basic state machine intent → RAG → respond → escalate if needed |
| 4 | **Production Tests** | 1 week | Tests for admin inbox routes, auth, email channel, conversations API. Without tests, any deploy risks regression |
| 5 | **Redis for Railway** | 2 days | Replace in-memory rate limiting/locks/queues with Redis for multi-instance safety |
| 6 | **Email + Stripe integration connectors** | 2 weeks | At minimum: SendGrid outbound (exists, needs testing) + inbound parse webhook. Stripe: invoice/payment event webhooks for PayGuard to react to |
| 7 | **Auto-seed config.yaml** | 1 day | Ensure sensible defaults so no manual config file creation needed on deploy |

### 3.3 MVP Should-Have (Week 2 post-launch)

| # | Item | Effort | Why |
|---|------|--------|-----|
| 1 | **Agent team management** | 1 week | Multiple operators per tenant with status (online/away) |
| 2 | **Widget unread badge** | 1 day | Proper unread tracking instead of mark-all-delivered |
| 3 | **Auto-CSAT trigger** | 1 day | Send rating widget after conversation closes |
| 4 | **Operator audit log** | 2 days | Track who assigned/closed/took over conversations |
| 5 | **SSE → WebSocket upgrade** | 1 week | Lower latency for inbox updates |
| 6 | **Sentry/error monitoring** | 1 day | Capture production errors |

### 3.4 MVP Nice-to-Have (Post-launch backlog)

| # | Item | Why Deferred |
|---|------|-------------|
| 1 | **Mobile SDK** | Web widget works in browser; native SDK is nice but not blocking |
| 2 | **HubSpot/CRM integration** | Enterprise feature, not MVP |
| 3 | **Co-browsing** | Differentiator but not essential for launch |
| 4 | **Multi-language** | Can launch with English; i18n can follow |
| 5 | **Role-based access control** | Single tenant = single admin for MVP |
| 6 | **Custom branding/themes** | Accent color + title exist; full theming can wait |

---

## 4. Technical Architecture Roadmap

### 4.1 Current Architecture

```
Customer Site                  Jeeves Backend
┌─────────────┐               ┌──────────────────────────────────┐
│ <jeeves-widget>│  POST     │  Widget Chat          ┌─────────┐│
│ Shadow DOM   │──/widget/chat→│  Intent Classifier   │ WISMO  ││
│ localStorage │  /widget/inbox│  ↓                    │ Workfl. ││
│ polling 15s  │               │  RAG / LLM / Workflow └─────────┘│
└─────────────┘               │  → Conversation + Message         │
                              │                                    │
Admin Browser                 │  Admin Panel                      │
┌─────────────┐               │  ┌────────────────────────────┐   │
│ Inbox (SSR) │  /admin/inbox  │  │ Inbox SSE ←→ Conversation  │   │
│ Agents page │               │  │ Customer Profile ← Customer│   │
│ Settings    │               │  │ Canned Responses           │   │
└─────────────┘               │  └────────────────────────────┘   │
                              │                                    │
External                      │  Integrations                     │
┌─────────────┐               │  ┌──────────┐  ┌──────────────┐  │
│ Shopify     │──webhooks────→│  │ Shopify  │  │ SendGrid     │  │
│ WhatsApp    │──webhook─────→│  │ Stripe*  │  │ Email (in)*  │  │
│ Email*      │──webhook─────→│  └──────────┘  └──────────────┘  │
└─────────────┘               └──────────────────────────────────┘
        * = not yet implemented
```

### 4.2 Target Architecture (MVP)

```
Customer Site                  Jeeves Backend (Railway)
┌─────────────┐               ┌──────────────────────────────────────┐
│ <jeeves-widget>│  POST     │  Widget Chat ─→ Intent Classifier     │
│ Shadow DOM   │──/widget/chat→│  ↓  ↓       ↓                       │
│ auto-baseUrl │  /widget/inbox│  │  │       ├── WISMO Workflow      │
│ polling 15s  │               │  │  └───────├── PayGuard Workflow   │
└─────────────┘               │  └──────────├── General Workflow     │
                               │              ↓ RAG / LLM            │
WhatsApp                      │  → Conversation + Message            │
┌─────────────┐               │  → Response to channel               │
│ WA Cloud API│──webhook─────→│                                      │
└─────────────┘               │  Email Channel (inbound)             │
                               │  ┌────────────────────────────────┐ │
Email                         │  │ SendGrid Inbound Parse Webhook  │ │
┌─────────────┐               │  │ → Create Conversation + Message │ │
│ support@... │──webhook─────→│  │ → Route to workflow             │ │
└─────────────┘               │  └────────────────────────────────┘ │
                               │                                      │
Admin Browser                 │  Admin Panel                          │
┌─────────────┐               │  ┌────────────────────────────────┐  │
│ Inbox       │  /admin/inbox  │  │ Inbox (SSE) + Customer Profile│  │
│ Workflows   │               │  │ Workflow Timeline + Escalation │  │
│ Settings    │               │  │ Canned Responses + Team Mgmt*  │  │
└─────────────┘               │  └────────────────────────────────┘  │
                               │                                      │
Redis                         │  Shared Infrastructure               │
┌─────────────┐               │  ┌──────────┐  ┌─────────────────┐  │
│ Rate Limits │               │  │ Redis    │  │ ChromaDB (RAG)  │  │
│ Queue       │               │  │ (locks,  │  │                 │  │
│ Locks       │               │  │  queue,  │  │ OpenAI API      │  │
└─────────────┘               │  │  idemp.) │  │ (LLM + embed)   │  │
                               │  └──────────┘  └─────────────────┘  │
                               └──────────────────────────────────────┘
                                        * = should-have, not must-have
```

### 4.3 New Models Required for MVP

```python
# PayGuard — payment recovery workflow
class PaymentAttempt(Base):
    """Tracks payment retry lifecycle."""
    __tablename__ = "payment_attempts"
    id, invoice_id (FK), workflow_id (FK), tenant_id (FK), customer_id (FK)
    attempt_number, method (card/bank/other), amount, currency
    status (pending/success/failed), failure_reason
    gateway_response (JSONB), created_at


# Email Inbound — incoming email processing
class EmailInbound(Base):
    """Tracks inbound email processing."""
    __tablename__ = "email_inbound"
    id, tenant_id (FK), conversation_id (FK)
    message_id (external), from_address, to_address, subject, body_text, body_html
    attachments (JSONB), processed, created_at


# Agent — operator identity model (replaces tenant.email as operator)
class Agent(Base):
    """Operator/agent identity for team inbox."""
    __tablename__ = "agents"
    id, tenant_id (FK)
    email, display_name, avatar_url
    role (admin/agent/viewer)
    status (online/away/offline)
    last_seen_at, created_at
```

### 4.4 Deployment Architecture (Railway)

```
                    Railway
┌─────────────────────────────────────────────────────┐
│  API Service (1 container)                          │
│  │── FastAPI app (gunicorn + uvicorn workers)       │
│  │── Routes: /widget/*, /admin/*, /auth/*, /chat    │
│  │── SSE: /admin/api/inbox/events                   │
│  │── Serves: widget.js, static files, landing page  │
│  │── Scale: 2-4 containers for HA                   │
│  ├──────────────────────────────────────────────────┤
│  Worker Service (1 container, WORKER_TYPE=scheduler)│
│  │── Workflow scheduler (due workflows)             │
│  │── Auto-close stale conversations                 │
│  │── Email inbound polling                          │
│  ├──────────────────────────────────────────────────┤
│  Redis (Railway add-on)                             │
│  │── Rate limiting, locks, queue, idempotency       │
│  ├──────────────────────────────────────────────────┤
│  PostgreSQL (Railway add-on)                        │
│  │── All application data                           │
│  └──────────────────────────────────────────────────┘
│  Optional: ChromaDB (Railway or external)           │
│  Optional: OpenAI API (external, required)          │
└─────────────────────────────────────────────────────┘
```

---

## 5. Implementation Roadmap

### Sprint 1 (Week 1-2): Foundation for New Workflows

| Day | Task |
|-----|------|
| 1-2 | Stripe webhook integration: invoice.created, payment_failed, payment_succeeded events → CanonicalEvent |
| 3-4 | PayGuard workflow: state machine (DETECTED → VALIDATING → RETRYING → DUNNING → RESOLVED/ESCALATED), retry logic, dunning email |
| 5 | PayGuard tests |
| 6-7 | General Support Workflow: simple state machine (RECEIVED → RESEARCHING → RESPONDING → RESOLVED/ESCALATED), RAG integration |

### Sprint 2 (Week 3-4): Channels + Infrastructure

| Day | Task |
|-----|------|
| 1-2 | Inbound email: SendGrid inbound parse webhook → Conversation + Message → route to workflow |
| 3 | Email channel tests |
| 4-5 | Redis migration: replace in-memory rate limiting, locks, queue with Redis |
| 6-7 | Production test suite: admin inbox routes, auth, conversations API, email channel |

### Sprint 3 (Week 5-6): Polish + Launch

| Day | Task |
|-----|------|
| 1 | config.yaml auto-seed + validation |
| 2 | Sentry/error monitoring |
| 3-4 | Agent team management (Agent model, assign-to-operator, status) |
| 5 | Widget unread badge fix, auto-CSAT trigger |
| 6 | End-to-end smoke tests, deployment docs |
| 7 | LAUNCH |

---

## 6. Open Questions for Decision

1. **Self-hosted vs SaaS?** — Jeeves is open source. Do we offer a managed SaaS (Railway) and self-hosted option? This affects pricing, support, and feature gating
2. **Pricing model?** — Competitors charge $0.50-$3.50/resolution. Jeeves' advantage is flat pricing. Options:
   - Free tier: 1 agent, 500 conversations/mo
   - Pro: $99/mo, 5 agents, unlimited conversations
   - Enterprise: Custom, self-hosted
3. **PayGuard: Stripe-native or generic?** — Build directly against Stripe API (fast, Stripe-only) or a generic payment gateway abstraction (slower, any gateway). MVP recommendation: Stripe-native
4. **Email: dedicated domain or shared?** — `support@store.com` (customer's domain, requires DNS config) vs `store@jeeves.ai` (shared, easier setup). MVP: both, with shared as default and custom domain as setting
5. **Widget: embed or iframe?** — Current: Web Component (Shadow DOM). Industry standard for Crisp/Intercom. Iframe would add isolation but breaks styling and increases complexity. Stick with Web Component
