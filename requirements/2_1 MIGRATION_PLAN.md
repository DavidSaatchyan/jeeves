# Migration Plan: Flat → Package-Based Structure

> **Target:** Directory layout defined in [System Architecture Specification](2%20SYSTEM_ARCHITECTURE.md#41-directory-layout-target)  
> **Based on:** Codebase analysis of current flat structure  
> **Estimated:** 5–7 working days  

---

## Overview

### Current structure (flat)
```
admin.py    1150 lines  — 9 concerns mixed
auth.py      241 lines  — 4 concerns mixed
knowledge.py 243 lines  — files + rag chat + cleanup
rag.py       255 lines  — self-contained
chunking.py  255 lines  — zero app deps
routes_chat.py 151 lines — llm call + webhook firing + chat
```

### Target structure (packages)
```
admin/        — 9 modules by concern
auth/         — 4 modules by concern
knowledge/    — files, chat, cleanup
rag/          — engine, chunking
chat/         — thin route handler
```

### Dependency Direction Rule (strict)

```
core/  →  models, config, db   (allowed)
admin/ →  core/, models, db    (allowed)
auth/  →  models, config, db   (allowed)
channels/ → core/ai, rag, models, db  (allowed)

forbidden:
core/  →  admin/, auth/, channels/, knowledge/
admin/ →  channels/ (except through core/)
```

---

## Phase 0: Fix Critical Bugs (1 day)

### What
Repair broken channel adapters before touching structure.

### Files to fix
| File | Bug | Fix |
|------|-----|-----|
| `channels/telegram.py` | `billing.enforce()` missing import + `agent.run()` (module missing) | **Delete file** — Telegram not in MVP, not planned |
| `channels/whatsapp.py` | Same bugs as telegram | Add `from .. import _simple_llm_response` (already imported but unused), add `from ..billing import enforce`, replace `agent.run()` with `_simple_llm_response()` |

### Risk
Low — both files have no router, no `app.include_router` in `main.py`. Deleting telegram breaks nothing. Fixing whatsapp enables it if wired later.

### Checklist
- [ ] Delete `channels/telegram.py`
- [ ] Fix `channels/whatsapp.py` imports and `agent.run()` call
- [ ] Update `channels/registry.py`: remove `"telegram"` from `SUPPORTED_CHANNELS`
- [ ] Update `.env`: remove `TELEGRAM_BOT_TOKEN`
- [ ] Update `config.yaml`: remove `telegram:` section
- [ ] Update `landing.html`: remove Telegram references
- [ ] Update `README.md`, `DEPLOY.md`
- [ ] `python -c "from app.main import app"` — passes

---

## Phase 1: Extract Core Shared Services (0.5 day)

### What
Move LLM and webhook logic out of route files into `core/` so both `chat/` and `channels/` can use them without importing route modules.

### Changes

```
routes_chat.py → thin route handler only
  _simple_llm_response()  →  core/ai/base.py:generate_chat_response()
  _fire_outgoing_webhooks() →  core/communications/webhooks.py
                         ←  routes_chat.py imports from core/ai/ + core/comms/
                         ←  widget.py imports from core/ai/ instead of routes_chat
```

### Files changed
| File | Change |
|------|--------|
| NEW `core/ai/base.py` | `generate_chat_response()` — extracted from `_simple_llm_response` |
| NEW `core/communications/webhooks.py` | `fire_outgoing_webhooks()` — extracted from `_fire_outgoing_webhooks` |
| `routes_chat.py` | Delete both functions, import from `core/` |
| `channels/widget.py` | Change `from ..routes_chat import _simple_llm_response` → `from ..core.ai.base import generate_chat_response` |
| `channels/whatsapp.py` | Same import change |

### Risk
Low — pure refactor, no logic changes. Each function's signature stays the same.

### Checklist
- [ ] `core/ai/base.py` created with `generate_chat_response()`
- [ ] `core/communications/webhooks.py` created with `fire_outgoing_webhooks()`
- [ ] `routes_chat.py` imports from new locations
- [ ] `widget.py` imports from `core/ai/base.py`
- [ ] `python -c "from app.main import app"` — passes
- [ ] `POST /chat` returns same responses
- [ ] `POST /widget/chat` returns same responses

---

## Phase 2: Split `admin.py` → `admin/` Package (2–3 days)

### What
Break 1150-line file into 9 concern-separated modules.

### Target structure
```
admin/
  __init__.py         # router = APIRouter(prefix="/admin")
  dep.py              # get_admin_tenant(), _admin_api_dep(), _ctx()
  pages.py            # 10 SSR page handlers: login, logout, agents, knowledge, …
  api_analytics.py    # GET  /admin/api/analytics
                      # GET  /admin/api/agents/{agent_type}/feed
                      # GET  /admin/api/agents/{agent_type}/funnel
  api_agents.py       # GET  /admin/api/workflows
                      # GET  /admin/api/workflows/{id}/timeline
                      # POST /admin/api/workflows/{id}/escalate
                      # GET  /admin/api/agents/{agent_type}/queue
                      # POST /admin/api/agents/{agent_type}/queue/resolve
                      # PUT  /admin/api/agents/{agent_type}/policy
  api_settings.py     # GET  /admin/api/settings
                      # PUT  /admin/api/settings
                      # POST /admin/api/settings/api-keys
                      # DELETE /admin/api/settings/api-keys/{id}
  api_billing.py      # GET  /admin/api/billing
  api_logs.py         # GET  /admin/api/logs
  api_ratings.py      # GET  /admin/api/ratings
                      # POST /admin/api/ratings
  api_policies.py     # GET  /admin/api/policies
                      # PUT  /admin/api/policies/{policy_type}
  api_integrations.py # GET  /admin/api/integrations
```

### Method
Per module: create file, copy function group, update imports, verify.

### Order (by independence)
```
1. dep.py           — no deps on other admin modules
2. api_billing.py   — 3 lines, imports billing module only
3. api_policies.py  — models.PolicySet only
4. api_logs.py      — models.ChatLog only
5. api_ratings.py   — models.ConversationRating only
6. api_integrations.py — models.NativeConnector + crypto
7. api_settings.py  — models.NotificationPreferences, ApiKey, Tenant + billing
8. api_analytics.py — models.Workflow, Escalation, Communication, AIInteraction
9. api_agents.py    — models.Workflow, TimelineEvent, Escalation, Customer, PolicySet
10. pages.py        — auth.decode_token, auth.issue_tokens, config
```

### Router aggregation (`__init__.py`)
```python
from fastapi import APIRouter
router = APIRouter(prefix="/admin")

from . import (
    api_analytics,
    api_agents,
    api_billing,
    api_logs,
    api_policies,
    api_ratings,
    api_settings,
    api_integrations,
)

# Page routes registered first
from .pages import login_page, admin_login, admin_logout, …
```

Each API module adds routes to the shared router via `@router.get(...)` within the module. Since `router` is imported from the package `__init__.py`, every module needs:

```python
from . import router  # shared router from admin/__init__.py
```

### Risk
Medium — highest risk phase. `admin.py` is coupled to 9 modules and 13 models. Each extracted function must be verified.

### Safety net
- `git checkout` for quick rollback
- Work in feature branch
- Run `python -c "from app.admin import router"` after each module
- Run `python -c "from app.main import app"` after all modules
- Test all admin API endpoints against dev db

### Checklist
- [ ] `admin/` directory created with `__init__.py`
- [ ] `dep.py` — dependencies extracted
- [ ] `pages.py` — all 10 page routes work
- [ ] `api_billing.py` — `/admin/api/billing` works
- [ ] `api_policies.py` — GET+PUT `/admin/api/policies` works
- [ ] `api_integrations.py` — GET `/admin/api/integrations` works
- [ ] `api_logs.py` — GET `/admin/api/logs` works
- [ ] `api_ratings.py` — GET+POST `/admin/api/ratings` works
- [ ] `api_settings.py` — settings + API keys CRUD works
- [ ] `api_analytics.py` — analytics + feed + funnel works
- [ ] `api_agents.py` — workflows + queue + resolve + policy works
- [ ] `admin.py` deleted
- [ ] `from app.admin import router` — passes
- [ ] `from app.main import app` — passes
- [ ] All admin pages render
- [ ] All admin API endpoints return 200

---

## Phase 3: Split `auth.py` → `auth/` Package (0.5 day)

### Target structure
```
auth/
  __init__.py  # router = APIRouter(prefix="/auth")
  dep.py       # get_current_tenant()
  tokens.py    # _issue(), issue_tokens(), decode_token(),
               # revoke_token(), is_token_revoked()
  api_keys.py  # _hash_key(), API key auth path
  routes.py    # register(), login(), refresh(), revoke()
  helpers.py   # _validate_password_strength(), _prepare_password(),
               # _get_client_ip()
```

### Risk
Low — 241 lines, clear concern boundaries, no circular imports.

### Checklist
- [ ] `auth/` directory with `__init__.py`
- [ ] `dep.py` — `get_current_tenant` works for JWT + API key
- [ ] `tokens.py` — token issuance and validation works
- [ ] `api_keys.py` — key hashing and verification works
- [ ] `routes.py` — register, login, refresh, revoke work
- [ ] `auth.py` deleted
- [ ] `from app.auth import router` — passes
- [ ] `POST /auth/register`, `/auth/login` work

---

## Phase 4: Split `knowledge/` + `rag/` (0.5 day)

### Target structure
```
knowledge/
  __init__.py  # router = APIRouter(prefix="/knowledge")
  files.py     # upload_file(), list_files(), delete_file()
  chat.py      # POST /knowledge/chat
  cleanup.py   # POST /knowledge/cleanup

rag/
  __init__.py  # exports: search, index_file, delete_file, dedup, purge
  engine.py    # ChromaClient, embed_batch, index, search, delete,
               # deduplicate_collection, purge_orphans
  chunking.py  # Chunk dataclass, build_chunks, _split_recursive,
               # sanitize_filename, file_sha256 (unchanged)
```

### Changes
| File | What Happens |
|------|-------------|
| `rag.py` | Move to `rag/engine.py`. Same code. |
| `chunking.py` | Move to `rag/chunking.py`. Same code. |
| `rag/__init__.py` | `from .engine import search, index_file, delete_file, deduplicate_collection, purge_orphans, embed_batch` |
| `knowledge/__init__.py` | `from .files import router` — routes registered in each submodule |
| `knowledge.py` | Deleted — split into `knowledge/files.py`, `knowledge/chat.py`, `knowledge/cleanup.py` |
| `main.py` | Update import path: `from .knowledge import router as knowledge_router` → `from .knowledge import router` |

### Risk
Low — `rag.py` has no app deps except `config`. `knowledge.py` imports from `rag` which stays at `from . import rag`.

### Checklist
- [ ] `rag/engine.py` — contains all Chroma logic
- [ ] `rag/chunking.py` — document chunking
- [ ] `rag/__init__.py` — re-exports public API
- [ ] `rag.py` deleted, `chunking.py` deleted
- [ ] `knowledge/files.py` — upload, list, delete
- [ ] `knowledge/chat.py` — POST /knowledge/chat
- [ ] `knowledge/cleanup.py` — POST /knowledge/cleanup
- [ ] `knowledge.py` deleted
- [ ] `from app.main import app` — passes
- [ ] `POST /knowledge/files` works
- [ ] `GET /knowledge/files` works
- [ ] `POST /knowledge/chat` works

---

## Phase 5: Update `main.py` + Verify All Imports (0.5 day)

### What
Update all `app.include_router()` calls and import paths in `main.py`.

### Before
```python
from . import admin, auth, integrations_routes, knowledge, routes_chat
from .integrations import webhooks as webhooks_router
from .channels import widget as widget_channel
```

### After
```python
from .admin import router as admin_router
from .auth import router as auth_router
from .knowledge import router as knowledge_router
from .chat import router as chat_router
from .integrations_routes import router as integrations_router
from .integrations import webhooks as webhooks_router
from .channels import widget as widget_channel
```

### Router registration
```python
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(knowledge_router)
app.include_router(widget_channel.router)
app.include_router(admin_router)
app.include_router(integrations_router)
app.include_router(webhooks_router.router)
```

### Checklist
- [ ] All import paths updated in `main.py`
- [ ] `from app.main import app` — passes
- [ ] All endpoints respond correctly

---

## Phase 6: Testing (1–2 days)

### Smoke tests (all critical paths)
| Test | What to check |
|------|---------------|
| App startup | `uvicorn app.main:app` starts without ImportError |
| Health | `GET /health` → 200 |
| Auth | register → login → access tokens work |
| Admin login | `POST /admin/login` → session set |
| Admin pages | All SSR routes render HTML |
| Admin API | `/admin/api/*` endpoints return valid JSON |
| Chat | `POST /chat` → response |
| Widget chat | `POST /widget/chat` → response (with RAG if KB exists) |
| Knowledge | Upload, list, delete files |
| Integrations | Connect/disconnect/test providers |
| Webhooks | Stripe/Shopify/Recharge webhook receivers |
| Workers | Scheduler, comms, workflow workers start |

### Regression check
- `grep -r "from app.admin import"` — should all be `from app.admin import router, dep, pages, ...`
- `grep -r "from app.auth import"` — should all be `from app.auth import router, dep, ...`
- No old flat file imports remain

---

## Summary: Timeline & Risk

| Phase | Days | Risk | Dependencies |
|-------|------|------|-------------|
| 0: Fix bugs | 1 | Low | None |
| 1: core/ai/ | 0.5 | Low | None |
| 2: admin/ | 2–3 | **Medium** | Phase 1 (cleaner imports) |
| 3: auth/ | 0.5 | Low | None |
| 4: knowledge/ + rag/ | 0.5 | Low | None |
| 5: main.py + imports | 0.5 | Low | Phases 2–4 complete |
| 6: Testing | 1–2 | Medium | All phases complete |
| **Total** | **5–7** | | |

### Parallelization
```
Day 1:   Phase 0 + Phase 1     (can be done together)
Day 2-4: Phase 2               (biggest chunk)
Day 3:   Phase 3 + Phase 4     (can overlap with end of Phase 2)
Day 4:   Phase 5               (after all splits done)
Day 5-6: Phase 6               (after everything merged)
```

### Rollback plan
If Phase 2 (admin split) causes too many issues:
- Keep old `admin.py` as-is
- Only do Phases 0, 1, 3, 4 (lower risk, still valuable)
- Revisit admin split later with more prep

---

## Pre-requisites

1. Feature branch `refactor/package-structure`
2. Dev database backup (for testing APIs)
3. At least one connected provider for integration testing
4. At least one uploaded file in KB for RAG testing
