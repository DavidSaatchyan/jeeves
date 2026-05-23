# Jeeves — AI Payment Recovery Agent

Autonomous AI agent for Shopify subscription brands that recovers failed subscription payments, communicates with customers across channels, and prevents churn — without requiring a support team.

## Quick start

### Production (Railway)
1. Push to `main` — Railway auto-deploys from root `Dockerfile`
2. Set required env vars in Railway dashboard:
   - `DATABASE_URL` — auto-set by Railway PostgreSQL
   - `OPENAI_API_KEY` — your OpenAI key
   - `JWT_SECRET` — random 32+ character string
   - `CHROMA_PATH` — `/data/chroma` (with Persistent Volume mounted)
3. Open your Railway domain

### Local development
```bash
cd api
pip install -r requirements.txt
# Set DATABASE_URL, OPENAI_API_KEY, JWT_SECRET in .env or environment
uvicorn app.main:app --reload
```

Open:
- **Admin dashboard:** http://localhost:8000/admin
- **API docs (OpenAPI):** http://localhost:8000/docs
- **Widget loader:** http://localhost:8000/widget.js

## Features

| Feature | Status | Notes |
|---------|--------|-------|
| PayGuard payment recovery agent | ✅ | Failed payment → classify → retry → recover |
| Payment failure detection (Stripe/Recharge webhooks) | ✅ | Canonical events → workflow creation |
| Failure classification (AI) | ✅ | Recoverable / semi-recoverable / blocked |
| Deterministic retry scheduling | ✅ | Configurable: max 3 attempts, 5min/1hr/24hr windows |
| Customer outreach (Email + Widget) | ✅ | Template-based, cadence-enforced, deduplicated |
| Sentiment analysis (AI) | ✅ | Frustration detection → escalation |
| Escalation management | ✅ | SLA tracking, assignment, resolve workflow |
| Policy engine | ✅ | Merchant-configured retry/comms/escalation rules |
| Knowledge base (PDF/TXT/MD upload) | ✅ | Async indexing → ChromaDB, RAG search |
| RAG search (ChromaDB + OpenAI embeddings) | ✅ | Cosine distance threshold filtering |
| Web chat widget | ✅ | Embeddable, origin-validated, rate-limited |
| Email channel (SendGrid/Resend) | ✅ | Outbound communication delivery |
| WhatsApp channel | ✅ | Webhook-based (integration pending final wiring) |
| Native integrations | ✅ | Shopify (read), Recharge (read+mutate), Stripe (read+retry) |
| Incoming/outgoing webhooks | ✅ | HMAC-SHA256 signed, field mapping |
| Conversation ratings | ✅ | Thumbs up/down with feedback |
| Admin dashboard | ✅ | Agents, analytics, connections, KB, channels, settings |
| JWT auth + API keys | ✅ | Access/refresh tokens, `sk_` API keys, bcrypt |
| Database migrations | ✅ | Alembic, auto-applied on startup |
| Rate limiting | ✅ | In-memory (dev) / Redis (prod) |
| Billing counters | ⚠️ | Hardcoded "free" plan, no payment collection (MVP) |
| Tests | ❌ | Removed in MVP cleanup — zero coverage |

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                   Jeeves Platform                      │
│                                                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │ Webhooks │─▶│  Event   │─▶│ Workflow │             │
│  │  Ingest  │  │Dispatcher│  │  Engine  │             │
│  └──────────┘  └──────────┘  └────┬─────┘             │
│                                    │                    │
│  ┌──────────┐  ┌──────────┐  ┌────▼──────┐            │
│  │  Policy  │  │    AI    │  │ Execution │             │
│  │  Engine  │  │ Classifier│  │ Dispatcher│             │
│  └──────────┘  └──────────┘  └────┬──────┘            │
│                                    │                    │
│  ┌──────────────────────────────────▼──────┐            │
│  │          Integrations Layer              │            │
│  │  Shopify  │  Recharge  │  Stripe        │            │
│  └─────────────────────────────────────────┘            │
│                                                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │ Channels │  │   RAG    │  │ Workers  │             │
│  │ Widget   │  │ ChromaDB │  │ Sched    │             │
│  │ Email    │  │          │  │ Comms    │             │
│  │ WhatsApp │  │          │  │ Events   │             │
│  └──────────┘  └──────────┘  └──────────┘             │
└──────────────────────────────────────────────────────┘
          │                     │
    ┌─────┴─────┐         ┌────┴────┐
    │ PostgreSQL │         │  Redis  │
    │ (Railway)  │         │(queue,  │
    │            │         │ locks,  │
    │            │         │scheduler)│
    └───────────┘         └─────────┘
```

### Core Principles
- **Deterministic execution** — LLM never executes operational actions (no state changes, no retries)
- **Idempotency** — all actions are retry-safe, deduplicated, replay-safe
- **Merchant control** — policies override AI suggestions
- **State ownership** — Stripe = payments, Recharge = subscriptions, Shopify = customers
- **Auditability** — every transition, message, retry, escalation logged

## Workers

Jeeves runs 4 background worker processes alongside the API:

| Worker | Entrypoint | Purpose |
|--------|-----------|---------|
| Scheduler | `app.workers.scheduler` | Polls Redis for due retry/expiry jobs |
| Event worker | `app.workers.event_worker` | Processes queued canonical events |
| Workflow worker | `app.workers.workflow_worker` | Executes scheduled workflow transitions |
| Comms worker | `app.workers.comms_worker` | Sends pending communications (email, widget) |

Each runs as a separate Railway service with `WORKER_TYPE` env distinguishing them.

## Project layout

```
Jeeves/
├── Dockerfile                  # Root-level build (api + frontend)
├── api/
│   ├── app/
│   │   ├── main.py             # FastAPI entrypoint, Alembic migrations
│   │   ├── models.py           # SQLAlchemy ORM models (source of truth)
│   │   ├── schemas.py          # Pydantic request/response schemas
│   │   ├── config.py           # Settings (env vars + config.yaml)
│   │   ├── db.py               # SQLAlchemy engine, session
│   │   ├── admin.py            # Admin panel SSR + JSON API (target: split to admin/)
│   │   ├── auth.py             # JWT auth, API keys (target: split to auth/)
│   │   ├── knowledge.py        # KB file management (target: split to knowledge/)
│   │   ├── rag.py              # ChromaDB + chunking (target: split to rag/)
│   │   ├── routes_chat.py      # Chat endpoint (target: split to chat/)
│   │   ├── billing.py          # Billing counters
│   │   ├── crypto.py           # Fernet credential encryption
│   │   ├── moderation.py       # Content moderation
│   │   ├── rate_limit.py       # Rate limiting (in-memory / Redis)
│   │   ├── integrations_routes.py  # Connector management API
│   │   │
│   │   ├── core/               # Agent Engine (the core)
│   │   │   ├── ai/             # LLM classification, generation, sentiment
│   │   │   ├── events/         # Canonical events, dispatch, dedup
│   │   │   ├── workflows/      # State machines, registry, runtime, scheduler
│   │   │   ├── policies/       # Retry, communication, escalation rules
│   │   │   ├── execution/      # Action dispatch, guards, idempotency
│   │   │   ├── commerce/       # Customer, subscription, invoice services
│   │   │   ├── communications/ # Message templates, delivery, dedup
│   │   │   ├── escalations/    # Escalation state machine, SLA
│   │   │   └── timeline/       # Audit trail
│   │   │
│   │   ├── channels/           # Widget, WhatsApp, Email
│   │   ├── integrations/       # Shopify, Recharge, Stripe clients
│   │   ├── shared/             # Queue, idempotency, locks
│   │   ├── workers/            # Background worker processes
│   │   └── templates/          # Jinja2 admin templates
│   ├── alembic/                # Database migrations
│   ├── alembic.ini
│   └── requirements.txt
├── frontend/
│   ├── widget.js               # Embeddable chat widget
│   └── widget.js.gz            # Compressed production version
├── knowledge/                  # Tenant KB files (git-ignored)
├── config.yaml                 # Agent prompts, model config, RAG params
├── AGENTS.md                   # AI-assisted development rules
├── DEPLOYMENT_CHECKLIST.md     # Production deployment checklist
└── requirements/               # Product requirements docs
    ├── 1 PRD.md
    ├── 2 SYSTEM_ARCHITECTURE.md
    ├── 2_1 MIGRATION_PLAN.md
    ├── 3 AGENT WORKFLOWS.md
    └── 4 WORKFLOW STATE MACHINE.md
```

## Embed widget on your site

```html
<script src="https://YOUR_DOMAIN/widget.js"
  data-tenant-id="YOUR_TENANT_ID"></script>
```

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | ✅ | PostgreSQL connection string |
| `OPENAI_API_KEY` | ✅ | OpenAI API key |
| `JWT_SECRET` | ✅ | 32+ character random string |
| `CHROMA_PATH` | ✅ | Path for ChromaDB persistent storage |
| `FERNET_KEY` | No | Key for credential encryption |
| `REDIS_URL` | No | Redis URL (queue, scheduling, rate limiting) |
| `PUBLIC_BASE_URL` | No | Public URL of your instance |
| `KNOWLEDGE_DIR` | No | Directory for uploaded files |
| `STRIPE_SECRET_KEY` | No | Stripe API key (payment recovery) |
| `SENDGRID_API_KEY` | No | SendGrid API key (email delivery) |
| `RESEND_API_KEY` | No | Resend API key (alt email delivery) |
| `RECHARGE_API_KEY` | No | Recharge API key (subscriptions) |
| `SHOPIFY_SHOP` | No | Shopify shop domain |
| `SHOPIFY_ACCESS_TOKEN` | No | Shopify access token |

## Database migrations

Migrations run automatically on startup via Alembic. To create a new migration:

```bash
cd api
alembic revision --autogenerate -m "description"
```

## PayGuard Workflow

```
Payment failed (webhook)
    │
    ▼
DETECTED → VALIDATING → CLASSIFYING_FAILURE (AI)
    │                           │
    │                    recoverable/blocked
    ▼                           │
SELECTING_STRATEGY        ESCALATED
    │
    ├──→ OUTREACH_PENDING → OUTREACH_SENT → WAITING_CUSTOMER
    └──→ RETRY_SCHEDULED → RETRY_PENDING → RETRYING → VERIFYING_RESULT
                                                              │
                                              ┌───────────────┼───────────────┐
                                              ▼               ▼               ▼
                                         RECOVERED      WAITING_CUSTOMER   FAILED
```

## Deployment

See [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md) for the complete production deployment checklist.

## AI-Assisted Development

See [AGENTS.md](AGENTS.md) for coding rules, architecture constraints, refactoring principles, and git workflow used in this project.

## License

Proprietary.
