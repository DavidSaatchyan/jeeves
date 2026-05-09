# Jeeves — Product Overview

## 1. Context

Jeeves is a self-serve, multi-tenant AI support agent platform. Tenants (businesses) register via a web portal, upload their knowledge-base documents, optionally connect CRM/native-integration systems, and embed a JavaScript chat widget on their website. End-users (customers of the tenant) interact with the widget, Telegram bot, or WhatsApp channel. The agent answers questions using RAG (Retrieval-Augmented Generation) over uploaded documents, CRM context, and incoming webhook data. It can execute configurable tools (lookups and actions) and escalate to human operators when needed.

**Target users:**
- **Tenants** — SaaS companies, e-commerce stores, service businesses that want AI-powered customer support.
- **End-users** — Customers of tenants who ask support questions via embedded widget or messaging channels.

**Current maturity:** MVP deployed on Railway (single-container). Phase 2 audit completed. Phase 3 (Stripe billing) pending.

---

## 2. Functional Blocks

### 2.1 Tenant Registration & Authentication (`auth.py`)
- Email/password registration with bcrypt hashing, password strength enforcement (8+ chars, mixed case, digit, special char).
- JWT access tokens (15 min TTL) and refresh tokens (7 day TTL).
- Session cookie set on `/admin` path after login/register.
- API key support (`sk_...` prefixed keys) for server-to-server auth, with SHA-256 hashing and optional expiry.
- Token revocation via Redis denylist (graceful fallback if Redis unavailable).
- Rate limiting on login (5/min/IP) and register (3/hr/IP).

### 2.2 Knowledge Base Manager (`knowledge.py`, `rag.py`, `chunking.py`)
- Upload PDF/TXT/MD files (max 50 MB per tenant).
- SHA-256 dedup: identical files return existing record.
- Token-aware + heading-aware chunking (`chunking.py`): respects PDF page boundaries, Markdown headings, and natural paragraph breaks.
- Embedding via OpenAI `text-embedding-3-small`.
- ChromaDB vector storage (cosine distance), per-tenant collections.
- Distance threshold filtering (0.85): results above threshold are discarded as irrelevant.
- Background indexing via `asyncio.create_task` — file marked `processing` → `ready`/`failed`.
- Re-indexing is idempotent (chunk IDs derived from `file_id + chunk_hash`).
- On delete: removes physical file, DB record, Chroma vectors, and clears conversation memory.

### 2.3 Agent Core (`agent.py`, `actions.py`, `memory.py`)
- Orchestrator using OpenAI tool-calling (`gpt-4o-mini`).
- Prompt assembly: system prompt + conversation history + XML-delimited RAG context + CRM context + webhook context.
- Max 5 iterations per message (tool call loop).
- Built-in tools: `get_subscription_status`, `update_tariff` (with confirmation gate), `escalate_to_human`.
- Custom tenant tools (lookup/action types) with URL templates, body templates, and parameter schemas.
- Conversation memory: sliding window (20 messages max, 7-day TTL), Redis-backed with in-memory fallback.
- Output sanitization: trailing question stripping, prompt injection detection and neutralization.

### 2.4 CRM Connector (`crm.py`, `hubspot.py`)
- Custom REST connector: configurable read/write URLs with JSONPath mapping.
- HubSpot OAuth connector with token refresh.
- Native connectors: Shopify (orders by email), WooCommerce (orders + customer), Stripe (subscription + next invoice).
- Customer lookup by email, user_id, or custom field (`primary_identifier`).
- 5-minute TTL read cache per tenant+user.
- SSRF protection: blocks private/internal IP ranges, localhost, cloud metadata endpoints.
- Write invalidates cache.

### 2.5 Channels (`channels/`)
- **Web Widget** (`widget.py` + `frontend/widget.js`): Embeddable JS with Shadow DOM, configurable theming, email capture, follow-up cards, rating cards, proactive inbox polling (15s interval), origin validation per tenant.
- **Telegram** (`telegram.py`): Webhook-based, bot token stored in `ChannelConfig`, O(1) tenant routing via `_ChannelLookupCache`.
- **WhatsApp** (`whatsapp.py`): Webhook-based, phone-number-ID routing, signature verification.
- **REST API** (`rest.py`): Direct API endpoint for programmatic access.
- Registry: `_ChannelLookupCache` provides O(1) lookups by bot_token (prefix matching) or phone_number_id, built on startup, invalidated on config changes.

### 2.6 Integrations (`routes_integrations.py`, `connectors/`, `webhooks.py`)
- **Native Connectors**: Shopify, WooCommerce, Stripe — credentials encrypted with Fernet, provision/deprovision auto-tools on connect/disconnect.
- **Incoming Webhooks**: HMAC-SHA256 signed POST to tenant's URL to enrich agent context with external data. JSONPath field mapping.
- **Outgoing Webhooks**: HMAC-SHA256 signed event notifications to tenant's URL.
- **Write-back Config**: Push conversation summaries to HubSpot notes or custom webhook on escalation.

### 2.7 Custom Agent Tools (`routes_tools.py`)
- CRUD for tenant-defined tools: lookups (GET) and actions (POST/PATCH/DELETE).
- URL templates with `{user_id}` interpolation.
- JSON body templates merged with LLM-provided parameters.
- Optional confirmation requirement for actions.
- Execution logging (request, response, latency, errors).

### 2.8 Admin Dashboard (`admin.py`, `templates/`, `dashboard_api.py`)
- SSR HTML pages (no `/v1/` prefix) with session-cookie auth.
- Stats: total dialogs, resolution rate, avg latency, ratings.
- Logs: paginated chat logs with cursor-based pagination (`last_id`).
- Knowledge base management: file list with status polling (5s interval), upload, delete, selection bar.
- CRM config: read/write URL setup, test connection.
- Channel management: widget, Telegram, WhatsApp activation.
- Billing panel: trial status, usage counters, plan info.

### 2.9 Proactive Engagement (`routes_proactive.py`)
- Monitors tenant-configured metric URL for percentage drops.
- Triggers proactive messages to widget inbox when drop exceeds threshold.
- Cooldown: minimum 3 days between triggers per user.

### 2.10 Billing (`billing.py`)
- Trial: 14 days or 100 dialogs (whichever comes first).
- Plans: Free ($0, 10 resolved), Starter ($19, 500), Pro ($49, 2,000), Enterprise ($149, 25,000).
- Overage: $0.10 per resolved dialog beyond plan limit.
- `test_widget` channel excluded from counters.
- ⚠️ **Stripe integration not yet implemented** — `_has_payment()` always returns `false`.

### 2.11 Moderation (`moderation.py`)
- Lightweight content policy check on incoming messages.
- Blocks messages violating content policy (400 response).

### 2.12 Rate Limiting (`rate_limit.py`)
- Sliding window rate limiter.
- Redis-backed for multi-instance; in-memory fallback for dev.
- Endpoint-specific limits: login (5/min), register (3/hr), chat (20/min), widget (20/min).

---

## 3. Feature Readiness & Gaps

Detailed assessment of webhooks, write-back, and custom tools — what works, what doesn't, limitations.

### 3.1 Incoming Webhooks

**Source:** `webhooks.py`

| Aspect | Status | Detail |
|--------|--------|--------|
| Config CRUD | ✅ | `GET`/`POST /integrations/webhook` — stores `incoming_url`, `incoming_secret` (Fernet), `field_mapping`, `enabled` |
| HMAC signing | ✅ | `X-Jeeves-Signature: sha256=...` computed on JSON body |
| Field mapping | ✅ | JSONPath expressions applied to tenant's response |
| Agent integration | ✅ | `fetch_incoming_webhook_context()` called in `agent.run()` step 1 (before RAG/CRM) |
| Graceful failure | ✅ | Timeout (5 s) / error → logs warning, returns `{}` — never blocks conversation |
| Admin UI | ❌ | No dashboard UI — API only |

**Limitations:**
- Called **once** at conversation start, not on every message.
- No retry logic — if tenant endpoint returns 500, context is silently lost.
- No custom headers support — only URL + secret + field mapping.
- `incoming_secret` is used only for signing; tenant cannot verify it server-side (Jeeves is the caller, not the receiver).

---

### 3.2 Outgoing Webhooks

**Source:** `webhooks.py`, `routes_integrations.py`

| Aspect | Status | Detail |
|--------|--------|--------|
| Config storage | ✅ | `outgoing_url`, `outgoing_secret` (Fernet), `events` list in `webhook_configs` |
| HMAC helper | ✅ | `compute_outgoing_signature()` — ready, correct |
| Event configuration | ✅ | `events` field — list of event names to fire on |
| **Fire / dispatch logic** | ❌ | **Not implemented.** `compute_outgoing_signature` exists but is never called to send anything. No code POSTs payload to `outgoing_url` on events. |

**What works:** Configuration CRUD, secret encryption, HMAC compute function.

**What does not work:** The actual sending mechanism. Missing:
- Event trigger hooks (on `escalated`, `resolved`, or custom events).
- Payload construction.
- HTTP POST to `outgoing_url`.
- Delivery logging or retry.

**Limitations:**
- No retry / dead-letter queue for failed deliveries.
- No admin UI for configuration.

---

### 3.3 Write-back Config

**Source:** `routes_integrations.py`, `models.py` (`WriteBackConfig`)

| Aspect | Status | Detail |
|--------|--------|--------|
| Config CRUD | ✅ | `GET`/`POST /integrations/writeback` |
| HubSpot note mode fields | ✅ | `hubspot_note_enabled`, `hubspot_task_on_escalation` stored in DB |
| Webhook mode fields | ✅ | `type: "webhook"` + `webhook_url` stored in DB |
| **Actual write-back execution** | ❌ | **Not implemented.** No code pushes conversation summary to HubSpot or webhook after dialog completion. |

**What works:** Full CRUD for configuration. Settings can be saved and retrieved via API.

**What does not work:**
- No code in `agent.run()` or middleware triggers summary push on conversation end.
- No HubSpot API call to create notes or tasks.
- No HTTP POST to `webhook_url` with summary payload.
- No summary template/format defined.

**Limitations:**
- No admin UI.
- Undefined summary schema — unclear what exact data to push.

---

### 3.4 Custom Agent Tools

**Source:** `routes_tools.py`, `connectors/registry.py`

| Aspect | Status | Detail |
|--------|--------|--------|
| CRUD | ✅ | `GET /tools`, `POST`, `PUT /{id}`, `DELETE /{id}` — full lifecycle |
| Unique name per tenant | ✅ | `_assert_unique_name()` on create/update |
| URL templating | ✅ | `{user_id}` + any LLM params via `str.format()` |
| Body templating | ✅ | `body_template` (JSONB) merged with dynamic params for POST/PATCH/PUT |
| Header management | ✅ | Static headers from config, merge logic on update |
| Confirmation gate | ✅ | `require_confirmation` → appends instruction to tool schema description |
| SSRF protection | ✅ | Dual-layer: save-time + runtime validation against private IPs |
| Test endpoint | ✅ | `POST /tools/{id}/test` — execute with arbitrary params |
| Execution logs | ✅ | `GET /tools/{id}/logs`, `GET /tools/logs/recent` — request/response/latency/error |
| OpenAI schema gen | ✅ | `build_tool_schemas()` → function-calling format, auto-injects `user_id` |
| Agent integration | ✅ | `dispatch_tool()` called from `agent.run()` loop |
| Native connector tools | ✅ | `connectors/registry.py` — auto-provision/deprovision tools on Shopify/Woo/Stripe connect/disconnect |

**Fully operational end-to-end.**

**Limitations:**
- **No pagination** on `/tools/logs/recent` — fixed `limit` (default 100), no cursor.
- **`native://` URLs don't dispatch via HTTP.** Tools provisioned for Shopify/Woo/Stripe use `native://shopify/...` scheme, but `_call_tool` only handles `http/https`. These tools are intended for a separate dispatch mechanism that does not exist yet. Currently, native data is read via `crm.read_customer()` pipeline, not through `AgentTool` execution.
- **No per-tool rate limiting** — tenant could create a tool that spams an external API.
- **Fixed 15 s timeout** — no per-tool customization.
- **No circuit breaker** — if external API is down, agent waits full timeout on every call.
- **No query param support** — params go only into URL template (`{}`) or body, not as `?key=value`.
- **No admin UI** for tool management — API only.

---

### 3.5 Readiness Summary

| Feature | Config | Execution | Agent Integration | Admin UI |
|---------|--------|-----------|-------------------|----------|
| Incoming Webhooks | ✅ | ✅ | ✅ | ❌ |
| Outgoing Webhooks | ✅ | ❌ | ❌ | ❌ |
| Write-back | ✅ | ❌ | ❌ | ❌ |
| Custom Tools | ✅ | ✅ | ✅ | ❌ |

---

## 4. Architecture Decision Records (ADRs)

### ADR-001: Single-Container Deployment
**Decision:** Deploy as a single Docker container running FastAPI + Uvicorn on Railway.
**Rationale:** MVP simplicity, low operational overhead. PostgreSQL and ChromaDB (persistent volume) are separate Railway services.
**Consequences:** No horizontal scaling without Redis. Background tasks use `asyncio.create_task` (not Celery) — lost on restart.

### ADR-002: Alembic Migrations on Startup
**Decision:** Run `alembic.command.upgrade("head")` in `on_startup` event.
**Rationale:** Zero-config migrations, no separate migration step in CI/CD.
**Consequences:** Startup slightly slower. Stamp fallback handles pre-existing tables from old `_MIGRATIONS` SQL.

### ADR-003: ChromaDB over Managed Vector DB
**Decision:** Use ChromaDB (embedded or HTTP client) instead of Pinecone/Weaviate.
**Rationale:** No external dependency, per-tenant collections, simple API. Sufficient for MVP scale.
**Consequences:** Chroma persistence tied to disk volume. No native multi-node support. Migration path needed at scale.

### ADR-004: OpenAI Tool-Calling over LangChain
**Decision:** Use OpenAI's native function-calling API directly.
**Rationale:** Fewer dependencies, simpler code, full control over prompt assembly and tool dispatch.
**Consequences:** Vendor lock-in to OpenAI. Switching LLM providers requires rewriting tool dispatch logic.

### ADR-005: XML-Delimited Context Injection
**Decision:** Wrap RAG, CRM, and webhook context in `<reference>` and `<user_message>` XML tags.
**Rationale:** Mitigates prompt injection by clearly separating data from instructions. LLMs understand XML structure.
**Consequences:** Relies on LLM compliance. Not a substitute for output validation (which is also applied).

### ADR-006: No `/v1/` Prefix for SSR Admin Routes
**Decision:** Admin HTML pages and their fetch calls use flat routes without `/v1/` prefix.
**Rationale:** Adding `/v1/` broke relative fetch calls in templates. Clean URLs for browser navigation.
**Consequences:** API versioning deferred until external clients appear. All internal APIs are currently unversioned.

### ADR-007: O(1) Channel Lookup Cache
**Decision:** Build in-memory `_ChannelLookupCache` on startup, indexed by bot_token and phone_number_id.
**Rationale:** Webhook routing needs to find tenant fast. Scanning all configs per webhook is O(n) and doesn't scale.
**Consequences:** Cache invalidated on config changes. Requires rebuild after any channel config update.

### ADR-008: Fernet Encryption for Credentials
**Decision:** Use Fernet (symmetric) for encrypting connector credentials and webhook secrets.
**Rationale:** Simple, reversible encryption. Single `FERNET_KEY` env var. Sufficient for MVP threat model.
**Consequences:** Key rotation requires re-encrypting all stored credentials. No per-tenant key isolation.

### ADR-009: In-Memory Memory Fallback
**Decision:** Conversation memory uses Redis when available, falls back to in-memory `deque`.
**Rationale:** Works out-of-the-box for local dev without Redis. Production gets persistent, multi-instance memory.
**Consequences:** In-memory memory is lost on restart and not shared across instances.

---

## 5. Database Schema

### Core Tables (15 tables)

| Table | Purpose | Key Relations |
|-------|---------|---------------|
| `tenants` | Tenant accounts, auth, billing counters | PK: `id` (UUID) |
| `crm_config` | Per-tenant CRM REST endpoint + JSONPath mapping | PK: `tenant_id` → `tenants.id` |
| `crm_action_logs` | Audit log for CRM read/write operations | `tenant_id` → `tenants.id` |
| `crm_connections` | HubSpot OAuth token storage | `tenant_id` → `tenants.id` |
| `proactive_metric` | Proactive engagement config per tenant | PK: `tenant_id` → `tenants.id` |
| `files` | Knowledge base file records + dedup hash | `tenant_id` → `tenants.id` |
| `agent_tools` | Tenant-defined custom tools | `tenant_id` → `tenants.id` |
| `agent_tool_logs` | Execution log for every tool call | `tenant_id` → `tenants.id`, `tool_id` → `agent_tools.id` |
| `chat_logs` | All conversation messages (incoming + outgoing) | `tenant_id` → `tenants.id` |
| `conversation_ratings` | User thumbs up/down + feedback | `tenant_id` → `tenants.id` |
| `native_connectors` | Encrypted credentials for Shopify/Woo/Stripe | `tenant_id` → `tenants.id`, UQ: `(tenant_id, provider)` |
| `webhook_configs` | Incoming/outgoing webhook URLs + HMAC secrets | PK: `tenant_id` → `tenants.id` |
| `writeback_configs` | Summary push to HubSpot or custom webhook | PK: `tenant_id` → `tenants.id` |
| `channels_config` | Per-tenant channel activation (widget/telegram/whatsapp) | `tenant_id` → `tenants.id`, UQ: `(tenant_id, channel_type)` |
| `api_keys` | Server-to-server API keys | `tenant_id` → `tenants.id` |

### Key Indexes
- `tenants.email` (unique)
- `files.content_hash` (dedup)
- `chat_logs.session_id` (conversation grouping)
- `api_keys.key_hash` (unique, for key lookup)

### Storage Outside PostgreSQL
- **ChromaDB:** Per-tenant vector collections (`tenant_<uuid>`) — stored on disk at `CHROMA_PATH` or remote via `CHROMA_URL`.
- **Knowledge files:** Local filesystem at `KNOWLEDGE_DIR/<tenant_id>/<file_id>/<filename>`.

---

## 6. C4 Architecture

### Level 1: System Context
```
┌─────────────┐     ┌──────────────────────────────────┐     ┌─────────────────┐
│  End-User    │────▶│                                  │────▶│  OpenAI API     │
│  (browser)   │     │          Jeeves Platform         │     │  (embeddings,   │
└─────────────┘     │                                  │     │   GPT-4o-mini)  │
                    │                                  │     └─────────────────┘
┌─────────────┐     │  ┌────────────┐  ┌────────────┐  │     ┌─────────────────┐
│  Tenant      │────▶│  │ FastAPI    │  │ PostgreSQL │  │◀───▶│  Tenant CRM     │
│  (admin)     │     │  │ + Uvicorn  │  │ (Railway)  │  │     │  (REST/HubSpot) │
└─────────────┘     │  └────────────┘  └────────────┘  │     └─────────────────┘
                    │         │                          │     ┌─────────────────┐
┌─────────────┐     │         ▼                          │     │  Native SaaS    │
│  Telegram    │────▶│  ┌────────────┐  ┌────────────┐  │◀───▶│  (Shopify/Woo/  │
│  /WhatsApp   │     │  │ ChromaDB   │  │ Knowledge  │  │     │   Stripe)       │
└─────────────┘     │  │ (volume)   │  │ Files      │  │     └─────────────────┘
                    │  └────────────┘  └────────────┘  │     ┌─────────────────┐
                    │                                  │◀───▶│  Tenant Webhook │
                    └──────────────────────────────────┘     │  Endpoints      │
                                                             └─────────────────┘
```

### Level 2: Container
```
┌──────────────────────────────────────────────────┐
│              Jeeves (Docker Container)            │
│                                                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │ FastAPI  │  │ Alembic  │  │ Channel Registry │ │
│  │ Routes   │──▶│ Migrate  │  │ (O(1) lookup)   │ │
│  └────┬─────┘  └──────────┘  └────────┬─────────┘ │
│       │                                │           │
│  ┌────┴────────────────────────────────┴─────┐    │
│  │              Agent Core                    │    │
│  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────────┐  │    │
│  │  │ RAG  │ │ CRM  │ │Tools │ │ Webhooks │  │    │
│  │  └──────┘ └──────┘ └──────┘ └──────────┘  │    │
│  └────────────────────────────────────────────┘    │
│       │           │           │                     │
│  ┌────┴───┐  ┌───┴────┐  ┌───┴─────┐              │
│  │ChromaDB│  │Memory  │  │Crypto   │              │
│  │Client  │  │(Redis) │  │(Fernet) │              │
│  └────────┘  └────────┘  └─────────┘              │
└──────────────────────────────────────────────────┘
```

### Level 3: Component (Agent Core)
```
┌─────────────────────────────────────────────────────────┐
│                    agent.run()                           │
│                                                          │
│  1. Fetch webhook context → webhooks.py                 │
│  2. Search RAG context → rag.py (ChromaDB)              │
│  3. Read CRM context → crm.py (cache → native → HubSpot │
│     → REST fallback)                                    │
│  4. Build prompt: system + history + <reference> +      │
│     <user_message>                                      │
│  5. OpenAI tool-calling loop (max 5 iterations)         │
│     ├── Built-in tools → actions.py                     │
│     └── Custom tools → routes_tools.py                  │
│  6. Sanitize output → strip questions, detect injection │
│  7. Return: response, action_called, escalated, sources │
└─────────────────────────────────────────────────────────┘
```

---

## 7. Sequence Diagrams

### 6.1 Tenant Registration → First Chat
```
Tenant Browser          Jeeves API              PostgreSQL    ChromaDB    OpenAI
     │                     │                        │            │           │
     │──POST /auth/register─▶│                        │            │           │
     │                     │──CREATE tenant─────────▶│            │           │
     │◀──JWT tokens────────│                        │            │           │
     │                     │                        │            │           │
     │──POST /knowledge/files─▶│                     │            │           │
     │                     │──INSERT file (processing)▶│         │           │
     │◀──{id, processing}──│                        │            │           │
     │                     │──[bg] chunk + embed ───────────────▶│           │
     │                     │──[bg] UPDATE file (ready)─────────▶│           │
     │                     │                        │            │           │
     │──POST /widget/chat─▶│                        │            │           │
     │                     │──INSERT chat_log──────▶│            │           │
     │                     │──rag.search() ─────────────────────▶│           │
     │                     │──crm.read() ──────────▶│            │           │
     │                     │──OpenAI completion ────────────────────────────▶│
     │                     │◀──response + tool calls────────────────────────│
     │                     │──UPDATE chat_log──────▶│            │           │
     │◀──{response}───────│                        │            │           │
```

### 6.2 Telegram Webhook Flow
```
Telegram Server    Jeeves API       Channel Cache    Agent    PostgreSQL
      │                │                 │             │          │
      │──POST /channels/                 │             │          │
      │  telegram/webhook─▶│             │             │          │
      │                │──lookup by      │             │          │
      │                │  token prefix──▶│──O(1)──────▶│          │
      │                │◀──tenant_id─────│             │          │
      │                │──billing.enforce()            │          │
      │                │──INSERT chat_log────────────▶│          │
      │                │──agent.run() ────────────────▶│          │
      │                │  (RAG + CRM + tools)          │          │
      │                │──UPDATE chat_log─────────────▶│          │
      │                │──Telegram sendMessage() ─────▶│          │
      │◀──200 OK──────│                                │          │
      │◀──message─────│                                │          │
```

### 6.3 Incoming Webhook Context Enrichment
```
Agent Core         webhooks.py        Tenant Webhook URL
     │                  │                     │
     │──fetch_context──▶│                     │
     │                  │──POST {tenant_id,    │
     │                  │  user_id, extras}    │
     │                  │  + X-Jeeves-Signature▶│
     │                  │◀──200 {custom_data}──│
     │                  │──apply field_mapping │
     │◀──context dict───│  (JSONPath)          │
```

### 6.4 Native Connector Provisioning
```
Tenant Admin    Jeeves API         crypto.py      DB         Connectors Registry
     │              │                  │            │                │
     │──POST /integrations/native─────▶│            │                │
     │  {provider, credentials}        │            │                │
     │              │──encrypt(Fernet)─▶│            │                │
     │              │◀──ciphertext─────│            │                │
     │              │──INSERT/UPDATE                │                │
     │              │  native_connectors───────────▶│                │
     │              │──provision_tools()────────────────────────────▶│
     │              │  (auto-create lookup/action tools)             │
     │◀──{ok}───────│                                                │
```

---

## 8. Non-Functional Requirements (NFRs)

| ID | Requirement | Current Status | Notes |
|----|-------------|----------------|-------|
| NFR-1 | **Multi-tenancy** — complete data isolation | ✅ | Tenant-scoped queries everywhere, `tenant_id` FK with CASCADE |
| NFR-2 | **Security** — no secrets in code/logs | ✅ | Fernet encryption, masked request logs, SSRF protection, HMAC webhooks |
| NFR-3 | **Availability** — graceful degradation | ✅ | Best-effort CRM/webhook reads (never block), fallback memory/rate-limiter |
| NFR-4 | **Performance** — sub-3s chat response | ⚠️ | Depends on OpenAI latency + RAG search. No SLA monitoring yet. |
| NFR-5 | **Scalability** — horizontal scaling | ⚠️ | Redis required for shared state (memory, rate limiting, token revocation). Single container limits concurrency. |
| NFR-6 | **Data retention** — conversation history TTL | ✅ | Memory: 7 days. Chat logs: no auto-purge (manual intervention needed). |
| NFR-7 | **KB freshness** — re-index on upload | ✅ | Background indexing, idempotent via chunk hash. |
| NFR-8 | **Accessibility** — widget a11y | ✅ | ARIA labels, roles, keyboard navigation (Escape to close), focus-visible outlines. |
| NFR-9 | **Privacy** — origin validation | ✅ | Strict origin check on widget endpoints, prevents tenant impersonation. |
| NFR-10 | **Auditability** — full action logging | ✅ | CRM action logs, agent tool logs, chat logs with sources trace. |
| NFR-11 | **Content safety** — input moderation | ✅ | Lightweight moderation filter on incoming messages. |
| NFR-12 | **Prompt safety** — injection defense | ✅ | XML delimiters, output validation, injection pattern detection. |

---

## 9. Risks

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| **Stripe billing not implemented** | High | Certain | Phase 3 priority. `_has_payment()` always returns `false`, so trial-exhausted tenants are permanently blocked. |
| **ChromaDB single-point-of-failure** | High | Medium | Disk corruption or volume loss wipes all vector data. Mitigation: regular Chroma volume snapshots. |
| **Background task loss on restart** | Medium | High | `asyncio.create_task` indexing tasks are lost if container restarts mid-index. Mitigation: add retry on startup for `processing` files. |
| **No horizontal scaling** | Medium | Medium | In-memory state (channel cache, rate limiter, CRM cache) not shared across instances. Redis partially mitigates this. |
| **OpenAI vendor lock-in** | Medium | Certain | Agent core, embeddings, and tool-calling all use OpenAI SDK. Abstraction layer needed for multi-provider support. |
| **Chat log growth unbounded** | Low | High | `chat_logs` table has no auto-purge. Will grow indefinitely. Mitigation: add TTL or archive job. |
| **`auth.py` duplicate `login` function** | Medium | Certain | Lines 215-255: `login` function is defined twice. Second definition shadows first. May cause subtle issues. |
| **Fernet key rotation complexity** | Low | Medium | Rotating `FERNET_KEY` requires decrypting and re-encrypting all stored credentials. No rotation mechanism exists. |
| **`secure=False` on login cookie** | Low | Fixed | Was identified and fixed during Phase 2 audit. Login cookie `secure=False` (needed for local dev). |
| **No API versioning** | Low | Medium | All APIs are unversioned. Breaking changes affect all clients simultaneously. `/v1/` planned for Phase 3. |

---

## 10. Glossary

| Term | Definition |
|------|------------|
| **Tenant** | A business/organization that uses Jeeves. Has its own KB, CRM config, channels, and billing. |
| **RAG** | Retrieval-Augmented Generation. Combines document search with LLM generation for factual answers. |
| **ChromaDB** | Open-source vector database used for storing and searching document embeddings. |
| **Embedding** | Vector representation of text (via OpenAI `text-embedding-3-small`). Used for similarity search. |
| **Chunk** | A segment of a document (512 tokens, 64 overlap) that gets embedded and stored in ChromaDB. |
| **Agent Tool** | A callable function the LLM can invoke: lookups (read-only) or actions (write). Can be built-in or tenant-defined. |
| **Channel** | A communication pathway: web widget, Telegram, WhatsApp, or REST API. |
| **Webhook (Incoming)** | Tenant's external endpoint that Jeeves calls to enrich conversation context. |
| **Webhook (Outgoing)** | Jeeves notifies tenant's endpoint about configured events (e.g., escalation). |
| **Native Connector** | Pre-built integration with Shopify, WooCommerce, or Stripe. Credentials encrypted with Fernet. |
| **CRM Config** | Per-tenant configuration for reading/writing customer data via REST + JSONPath mapping. |
| **Write-back** | Pushing conversation summaries to CRM (HubSpot note) or custom webhook after resolution/escalation. |
| **Proactive Message** | Outgoing message triggered by metric drop detection, delivered to widget inbox. |
| **Fernet** | Symmetric encryption scheme (AES-128-CBC + HMAC-SHA256). Used for credential storage. |
| **SSRF** | Server-Side Request Forgery. Mitigated by blocking private IP ranges in CRM URL validation. |
| **HMAC-SHA256** | Hash-based Message Authentication Code. Used for webhook request signing. |
| **Alembic** | Database migration tool for SQLAlchemy. Runs on startup to keep schema current. |
| **O(1) Lookup** | Constant-time channel routing via pre-built in-memory hash map (token/phone → tenant_id). |
| **Cursor Pagination** | Pagination using `last_id` instead of offset, for consistent results on frequently-changing data. |
| **Shadow DOM** | Web API used by widget to isolate CSS from the host page. |
