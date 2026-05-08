# Jeeves — Universal AI Agent

Self-serve AI support agent: tenant-isolated RAG over uploaded docs, CRM connector (read/write), web chat widget, omnichannel support (Telegram, WhatsApp), and admin dashboard.

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

## Embed widget on your site

```html
<script src="https://YOUR_DOMAIN/widget.js"
  data-tenant-id="YOUR_TENANT_ID"></script>
```

## Architecture

```
┌──────────────────────────────────────────┐
│           Railway (production)           │
│                                          │
│  ┌──────────────┐   ┌─────────────────┐  │
│  │  API Service │   │  PostgreSQL     │  │
│  │  FastAPI     │◄─►│  Railway managed│  │
│  │  Uvicorn     │   │                 │  │
│  └──────┬───────┘   └─────────────────┘  │
│         │                                 │
│  ┌──────┴───────┐                         │
│  │ Chroma vol.  │  Persistent Disk         │
│  │ /data/chroma │  survives redeploys      │
│  └──────────────┘                         │
└──────────────────────────────────────────┘
```

All endpoints share a common root. Widget endpoints (`/widget/`) remain public for embeds.
API versioning (`/v1/`) is planned for when external clients appear.

## Features

| Feature | Status | Notes |
|---------|--------|-------|
| Tenant registration & auth (JWT) | ✅ | `/v1/auth/register`, `/v1/auth/login` |
| Knowledge base (PDF/TXT/MD upload) | ✅ | Async background indexing via `asyncio` |
| RAG search (ChromaDB + OpenAI embeddings) | ✅ | Cosine distance threshold filtering |
| CRM connector (read/write) | ✅ | Custom REST + HubSpot OAuth |
| Agent tool calling (HTTP actions) | ✅ | CRUD in dashboard, confirmed actions |
| Web chat widget | ✅ | Embeddable, origin-validated |
| Telegram channel | ✅ | Webhook-based, O(1) routing |
| WhatsApp channel | ✅ | Webhook-based |
| Native integrations (Shopify, WooCommerce) | ✅ | Credential storage with encryption |
| Incoming webhooks (context enrichment) | ✅ | HMAC-SHA256 signed |
| Outgoing webhooks (event notifications) | ✅ | HMAC-SHA256 signed |
| Conversation ratings | ✅ | Thumbs up/down with feedback |
| Admin dashboard | ✅ | Stats, logs, billing, config |
| Database migrations | ✅ | Alembic, applied on startup |
| API versioning | ⏳ | Planned for external client launch |
| Rate limiting | ✅ | In-memory (dev) / Redis (prod) |
| Billing | ⚠️ | Internal counters, hardcoded "free" plan |

## Project layout

```
Jeeves/
├── Dockerfile              # Root-level build (api + frontend)
├── api/
│   ├── app/
│   │   ├── main.py         # FastAPI entrypoint, Alembic migrations
│   │   ├── agent.py        # Agent orchestrator (RAG + CRM + tools)
│   │   ├── rag.py          # ChromaDB indexing & search
│   │   ├── memory.py       # Conversation memory
│   │   ├── models.py       # SQLAlchemy ORM models
│   │   ├── channels/       # Widget, Telegram, WhatsApp handlers
│   │   ├── crm.py          # CRM REST connector
│   │   ├── templates/      # Admin dashboard HTML
│   │   └── ...
│   ├── alembic/            # Database migrations
│   ├── tests/              # Unit & integration tests
│   └── requirements.txt
├── frontend/
│   ├── widget.js           # Embeddable chat widget
│   ├── dashboard.js        # Admin dashboard JS
│   └── dashboard.css
├── knowledge/              # Tenant KB files (git-ignored)
├── config.yaml             # Agent prompts, model config
└── scripts/
    └── test_api.sh         # Smoke test script
```

## Tests

```bash
cd api
pytest tests/
```

## Database migrations

Migrations run automatically on startup via Alembic. To create a new migration:

```bash
cd api
alembic revision --autogenerate -m "description"
```

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | ✅ | PostgreSQL connection string |
| `OPENAI_API_KEY` | ✅ | OpenAI API key |
| `JWT_SECRET` | ✅ | 32+ character random string |
| `CHROMA_PATH` | ✅ | Path for ChromaDB persistent storage |
| `REDIS_URL` | No | Redis URL for production rate limiting & memory |
| `PUBLIC_BASE_URL` | No | Public URL of your instance |
| `KNOWLEDGE_DIR` | No | Directory for uploaded files |
| `HUBSPOT_CLIENT_ID` | No | HubSpot OAuth client ID |
| `HUBSPOT_CLIENT_SECRET` | No | HubSpot OAuth client secret |

## License

Proprietary.
