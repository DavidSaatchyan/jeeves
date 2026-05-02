# Jeeves — Universal AI Agent (MVP)

Self-serve AI support agent: tenant-isolated RAG over uploaded docs, CRM connector (read/write), web chat widget, proactive engine for metric drops, and admin dashboard.

## Quick start

```bash
cp .env.example .env
# put your OPENAI_API_KEY and a JWT_SECRET into .env
docker compose up --build
```

Open:
- Admin dashboard: http://localhost:8000/admin
- API docs (OpenAPI): http://localhost:8000/docs
- Widget loader: http://localhost:8000/widget.js

## Acceptance scenarios (MVP OKR)

1. **Register** — POST `/auth/register` or use `/admin` form → receive JWT, see dashboard.
2. **Upload KB** — drag-and-drop `.pdf/.txt/.md` in dashboard → worker indexes into Chroma → ask question in chat.
3. **CRM** — set read/write URLs + header token → "Test" button → say "change my tariff to business" → agent calls CRM.
4. **Widget** — paste `<script src="http://localhost:8000/widget.js" data-tenant-id="<YOUR_TENANT_ID>"></script>` onto any page.
5. **Proactive** — configure metric URL + threshold → Celery beat checks hourly → agent posts "need help?" message.
6. **Billing** — after 100 dialogs or 14 days API returns 402 Payment Required.
7. **Resolution rate** — visible on dashboard.

## Project layout

```
jeeves-mvp/
├── docker-compose.yml
├── .env.example
├── config.yaml
├── api/                 # FastAPI service
│   └── app/
├── worker/              # Celery worker + beat
├── frontend/widget.js   # Embeddable chat widget
├── knowledge/           # Mounted dir for uploaded files
└── scripts/
    ├── init_db.sql
    └── test_api.sh
```

## Sensible defaults chosen (see code comments marked `# DEFAULT`)

- **Email verification** — stubbed: verification link is printed to API stdout, account is immediately active.
- **Admin dashboard** — server-rendered Jinja2 + HTMX (no SPA) to keep MVP lean.
- **File storage** — local filesystem under `./knowledge/{tenant_id}/{file_id}/` (S3 path is wired but optional).
- **Billing** — internal counters + `is_active` flag, no real Stripe yet. Endpoint returns 402 when limits exceeded.
- **Memory** — Redis list per `memory:{tenant_id}:{user_id}`, TTL 7 days, last 20 messages.
- **Vector DB** — one Chroma collection per tenant (`tenant_{uuid}`).
- **Proactive** — Celery beat runs every hour; agent posts "outgoing" log row, widget/SSE picks it up via `GET /chat/inbox`.

## Tests

```bash
bash scripts/test_api.sh
```
