# Integration Gateway — Cliniko + CRM-Agnostic Booking

## Goal
Сделать систему **CRM-agnostic**: убрать прямую привязку `core/booking/` к `PabauConnector`, внедрить **Integration Gateway** (resolver), который сам выбирает коннектор по настройкам тенанта. Добавить `ClinikoConnector` как второго провайдера.

## Принцип
```
core/booking/  →  get_crm_adapter(tenant_id)  →  PabauConnector | ClinikoConnector
channels/      →  get_crm_adapter(tenant_id)  →  PabauConnector | ClinikoConnector
admin/         →  get_crm_adapter(tenant_id)  →  PabauConnector | ClinikoConnector
```

---

## Phase 1: Gateway Layer (рефакторинг без новой функциональности)

### 1.1 Модель Tenant — универсальные поля CRM
**File:** `api/app/models.py`

- `pabau_config` (JSONB) → `crm_config` (JSONB) — `migration rename`
- Добавить `crm_provider` (String, default `"pabau"`)
- Старые данные: миграция переносит `pabau_config` → `crm_config`, ставит `crm_provider = "pabau"`
- Все ссылки `tenant.pabau_config` → `tenant.crm_config`

**Migration:** Alembic revision:
```python
op.add_column("tenants", Column("crm_config", JSONB, default=dict))
op.add_column("tenants", Column("crm_provider", String(50), default="pabau"))
op.execute("UPDATE tenants SET crm_config = pabau_config, crm_provider = 'pabau'")
op.drop_column("tenants", "pabau_config")
```

### 1.2 Resolver — `get_crm_adapter()`
**File:** `api/app/integrations/resolver.py` (NEW)

```python
CRM_PROVIDERS: dict[str, type[AbstractCrmConnector]] = {
    "pabau": PabauConnector,
    "cliniko": ClinikoConnector,
}

def get_crm_adapter(tenant_id: UUID, db: Session) -> AbstractCrmConnector | None:
    tenant = db.get(Tenant, tenant_id)
    if not tenant or not tenant.crm_config:
        return None
    provider = tenant.crm_provider or "pabau"
    cls = CRM_PROVIDERS.get(provider)
    if not cls:
        return None
    return cls(tenant.crm_config)
```

- `PabauConnector.__init__` остаётся без изменений (принимает `config: dict`)
- `ClinikoConnector.__init__` принимает тот же `config: dict`

### 1.3 API Connector — добавить `test_connection()` в базовый класс
**File:** `api/app/integrations/base.py`

- Добавить метод `test_connection() -> bool` в `AbstractCrmConnector`
- `PabauConnector.test_connection()` — `GET /patients?limit=1`
- `ClinikoConnector.test_connection()` — `GET /v1/practitioners?per_page=1`

### 1.4 Обновить всех потребителей (consumers)

| File | Что меняется |
|------|-------------|
| `core/booking/__init__.py` | `_get_pabau_adapter()` → `_get_crm_adapter()` из `integrations.resolver` |
| `core/booking/slot_manager.py` | `get_available_slots()` — убрать прямой `from ..integrations.pabau import PabauConnector`, использовать `get_crm_adapter()` |
| `channels/whatsapp.py` | `_maybe_crm_bridge()` — заменить прямой `PabauConnector` на `get_crm_adapter()` |
| `integrations/webhooks.py` | Заменить прямой `PabauConnector` на `get_crm_adapter()` |
| `integrations/__init__.py` | Экспортировать `get_crm_adapter` |

### 1.5 Admin: обобщить Pabau settings
**Files:** `api/app/admin/pabau.py`, `api/app/templates/pabau_connections.html`

- GET `/admin/pabau` теперь показывает `crm_provider` + `crm_config`
- POST `/admin/api/crm/configure` — принимает `provider: str` + `config: dict`
- POST `/admin/api/crm/test` — вызывает `adapter.test_connection()` через resolver
- POST `/admin/api/crm/disconnect` — очищает `crm_config`
- rename из `pabau` в `crm` в URL-префиксе

### 1.6 Config: Cliniko secrets
**File:** `api/app/config.py`

- Добавить `cliniko_api_key: str = ""`
- `cliniko_user_agent: str = "Jeeves (devs@jeeves.ai)"`
- `pabau_api_key` оставить (используется для `PabauConnector`)

### 1.7 Webhooks: Cliniko роутер
**File:** `api/app/main.py`

- Добавить эндпоинт `POST /integrations/webhooks/cliniko/{tenant_id}`
- Cliniko webhooks: appointment.created, appointment.updated, appointment.cancelled, patient.created, patient.updated

### 1.8 Router: Cliniko admin pages
**File:** `api/app/admin/__init__.py`

- Добавить `from . import cliniko`
- Создать `api/app/admin/cliniko.py` — страница настроек Cliniko

---

## Phase 2: ClinikoConnector

### 2.1 Файл: `api/app/integrations/cliniko.py`

**Authentication:**
- HTTP Basic Auth (API key как username, пустой password)
- Header: `Authorization: Basic base64(key + ":")`
- Required: `User-Agent` header (из конфига)
- Required: `Accept: application/json`

**Base URL:** `https://api.{shard}.cliniko.com/v1/`
- shard берётся из `crm_config["shard"]` (по умолчанию `"au1"`)

**Rate Limiting:**
- 200 req/min per user
- 429 → `ConnectorRateLimitError`
- `X-RateLimit-Reset` header

**Pagination:**
- `page` + `per_page` (max 100)
- `total_entries` в ответе
- `links.next/self/previous`

**Filtering:**
- `q[]` параметр: `q[]=field:operator:value`
- Дата/время: `updated_at:>2026-01-01T00:00:00Z`
- Строка: `first_name:~value` (contains)

### 2.2 Реализуемые методы

| Метод | Cliniko API | Заметки |
|-------|-------------|---------|
| `__init__(config)` | — | Читает `api_key`, `shard`, `user_agent` |
| `_headers()` | — | Basic Auth + Accept + User-Agent |
| `_request()` | — | обёртка над httpx с обработкой 401/404/429/5xx |
| `test_connection()` | `GET /v1/practitioners?per_page=1` | Проверка API ключа |
| `find_patient(email, phone)` | `GET /v1/patients?q[]=email:=X` или `q[]=mobile:=X` | Возвращает первого совпавшего |
| `get_patient(id)` | `GET /v1/patients/{id}` | — |
| `create_patient(data)` | `POST /v1/patients` | Маппинг полей Pabau→Cliniko |
| `update_patient(id, data)` | `PUT /v1/patients/{id}` | — |
| `get_appointment(id)` | `GET /v1/individual_appointments/{id}` | — |
| `create_appointment(patient_id, data)` | `POST /v1/individual_appointments` | `patient_id` в `patient_id`, маппинг полей |
| `update_appointment(id, data)` | `PUT /v1/individual_appointments/{id}` | — |
| `cancel_appointment(id)` | `PUT /v1/individual_appointments/{id}` с `cancelled_at` | Cliniko не DELETE, а PUT с cancelled_at |
| `list_appointments(tenant_id, status, ...)` | `GET /v1/individual_appointments` с фильтрами `q[]` | Фильтрация через `q[]` |
| `get_patient_appointments(patient_id)` | `GET /v1/individual_appointments?q[]=patient_id:=X` | — |
| `search_available_slots(doctor_id, date)` | `GET /v1/available_times?q[]=practitioner_id:=X&q[]=date:=Y` | Cliniko возвращает готовые слоты |
| `verify_webhook_signature(payload, sig)` | — | Cliniko не подписывает вебхуки (пока) — `return True` |
| `parse_webhook_event(payload)` | Парсинг события | Маппинг Cliniko формата в канонический |

### 2.3 Маппинг полей

**Patient: Pabau → Cliniko**

| Наше поле | Pabau поле | Cliniko поле |
|-----------|-----------|-------------|
| `first_name` | `first_name` | `first_name` |
| `last_name` | `last_name` | `last_name` |
| `email` | `email` | `email` |
| `phone` | `phone` | `mobile` |
| `date_of_birth` | `date_of_birth` | `date_of_birth` |
| `gender` | `gender` | `gender` |
| `notes` | `notes` | `notes` |

**Appointment: Pabau → Cliniko**

| Наше поле | Pabau поле | Cliniko поле |
|-----------|-----------|-------------|
| `patient_id` | `patient_id` | `patient_id` (URL: `/v1/patients/X`) |
| `practitioner_id` | `provider_name` | `practitioner_id` (URL: `/v1/practitioners/X`) |
| `start_time` | `start_time` | `starts_at` |
| `end_time` | `end_time` | `ends_at` |
| `notes` | `reason` | `notes` |
| `status` | `status` | выводится из `cancelled_at` (если set → cancelled) |
| `appointment_type_id` | — | `appointment_type_id` (URL: `/v1/appointment_types/X`) |

### 2.4 Cliniko специфика

- **Practitioners** — получаем список `GET /v1/practitioners` для маппинга `provider_name` → `practitioner_id`
- **Appointment Types** — `GET /v1/appointment_types` для маппинга service → appointment_type_id
- **Available Times** — `GET /v1/available_times?q[]=practitioner_id:=X&q[]=date:=YYYY-MM-DD` — возвращает готовые свободные окна
- **Отмена встречи:** не `DELETE`, а `PUT /v1/individual_appointments/{id}` с `cancelled_at: "2026-..."` и `cancellation_reason`
- **Webhooks:** Cliniko поддерживает вебхуки, но формат другой — тело напрямую, без подписи

---

## Phase 3: Admin UI

### 3.1 Cliniko settings page
**File:** `api/app/admin/cliniko.py` (NEW)

- GET `/admin/cliniko` — форма: API Key, Shard, User-Agent
- POST `/admin/api/cliniko/configure` — сохраняет `crm_provider = "cliniko"` + `crm_config`
- POST `/admin/api/cliniko/test` — `GET /v1/practitioners?per_page=1`
- POST `/admin/api/cliniko/disconnect` — очищает `crm_config`

### 3.2 Template
**File:** `api/app/templates/cliniko_connections.html` (NEW)

- Поля: API Key, Shard (select: au1, eu1, us1 и т.д.)
- User-Agent показывается, но редактируется только через env
- Тест-коннект кнопка

### 3.3 Sidebar
**File:** `api/app/templates/base.html`

- "Pabau" → "Integrations" с выпадающим списком (Pabau, Cliniko) или отдельными пунктами

### 3.4 Router
**File:** `api/app/main.py`

- Cliniko admin router: `app.mount("/admin", cliniko_router)`
- Cliniko webhook router: `app.include_router(cliniko_webhook_router, prefix="/integrations/webhooks")`

---

## Phase 4: Tests

### 4.1 ClinikoConnector unit tests
**File:** `api/tests/test_cliniko_connector.py` (~35 tests)

| Группа | Тесты |
|--------|-------|
| Init | конструктор с config, shard по умолчанию, user-agent |
| _request | GET возвращает JSON, Basic Auth заголовки, 401→AuthError, 404→NotFound, 429→RateLimit, 500→ConnectorError, network error |
| Patients | get/find/create/update, маппинг полей |
| Appointments | create/cancel/update/get/list, маппинг, cancelled_at для отмены |
| Slots | search_available_slots (GET /available_times, парсинг ответа) |
| Webhooks | verify_signature (всегда true), parse_webhook_event |
| Practitioners | get_practitioners (кэширование) |

### 4.2 Resolver tests
**File:** `api/tests/test_crm_resolver.py` (~8 tests)

| Тест | Описание |
|------|----------|
| returns_pabau_connector | tenant с `crm_provider="pabau"` → PabauConnector |
| returns_cliniko_connector | tenant с `crm_provider="cliniko"` → ClinikoConnector |
| returns_none_no_config | tenant без `crm_config` → None |
| returns_none_unknown_provider | tenant с `crm_provider="unknown"` → None |
| returns_none_no_tenant | tenant_id не найден → None |
| passes_config_to_connector | config из тенанта передаётся в конструктор |

### 4.3 Обновить booking e2e тесты
**File:** `api/tests/test_booking_e2e.py`

- Моки `get_crm_adapter()` вместо `_get_pabau_adapter`
- Добавить тесты с `crm_provider="cliniko"`

### 4.4 Обновить whatsapp messaging тесты
**File:** `api/tests/test_whatsapp_messaging.py`

- `test_maybe_crm_bridge` → мок `get_crm_adapter()` вместо `PabauConnector`

---

## Migration Safety

| Риск | Митигация |
|------|-----------|
| Существующие Pabau-тенанты потеряют конфиг | Миграция: `crm_config = pabau_config`, `crm_provider = 'pabau'` |
| Старый код ссылается на `tenant.pabau_config` | `grep -r "pabau_config" api/` — все reference обновить |
| Cliniko API key в env | Добавить `cliniko_api_key` в `_validate_secrets()` (опционально) |
| Webhook роуты пересекаются | `/integrations/webhooks/pabau/{id}` и `/integrations/webhooks/cliniko/{id}` |

---

## Files Changed/Added

| File | Action |
|------|--------|
| `api/app/models.py` | EDIT: rename `pabau_config`→`crm_config`, add `crm_provider` |
| `api/app/config.py` | EDIT: add `cliniko_api_key`, `cliniko_user_agent` |
| `api/app/integrations/base.py` | EDIT: add `test_connection()` |
| `api/app/integrations/resolver.py` | **NEW** |
| `api/app/integrations/cliniko.py` | **NEW** |
| `api/app/integrations/pabau.py` | EDIT: add `test_connection()` |
| `api/app/integrations/__init__.py` | EDIT: export `get_crm_adapter` |
| `api/app/integrations/webhooks.py` | EDIT: use `get_crm_adapter()` |
| `api/app/core/booking/__init__.py` | EDIT: `_get_pabau_adapter` → `_get_crm_adapter` |
| `api/app/core/booking/slot_manager.py` | EDIT: use `get_crm_adapter()` |
| `api/app/channels/whatsapp.py` | EDIT: use `get_crm_adapter()` |
| `api/app/admin/pabau.py` | EDIT: rename routes, use `crm_config` |
| `api/app/admin/cliniko.py` | **NEW** |
| `api/app/admin/__init__.py` | EDIT: add cliniko import |
| `api/app/templates/pabau_connections.html` | EDIT: update for `crm_config` |
| `api/app/templates/cliniko_connections.html` | **NEW** |
| `api/app/templates/base.html` | EDIT: update sidebar |
| `api/app/main.py` | EDIT: add cliniko webhook router |
| `api/tests/test_cliniko_connector.py` | **NEW** (~35 tests) |
| `api/tests/test_crm_resolver.py` | **NEW** (~8 tests) |
| `api/tests/test_booking_e2e.py` | EDIT: mock `get_crm_adapter` |
| `api/tests/test_whatsapp_messaging.py` | EDIT: mock `get_crm_adapter` |
| Alembic migration | **NEW** (rename column) |

---

## Execution Order

```
Phase 1 (Gateway):
  1.1 models.py → rename + add crm_provider
  1.2 resolver.py → NEW
  1.3 base.py → add test_connection()
  1.4 all consumers → use get_crm_adapter()
  1.5 admin/pabau.py → generalize
  1.6 config.py → cliniko_api_key
  → VERIFY: from app.main import app, pytest

Phase 2 (Cliniko):
  2.1 cliniko.py → NEW
  2.2 webhooks.py → add cliniko routes
  → VERIFY: pytest test_cliniko_connector.py

Phase 3 (Admin UI):
  3.1 admin/cliniko.py → NEW
  3.2 cliniko_connections.html → NEW
  3.3 base.html → update sidebar
  → VERIFY: pytest, manual /admin/cliniko

Phase 4 (Tests):
  4.1 test_cliniko_connector.py
  4.2 test_crm_resolver.py
  4.3 update test_booking_e2e.py
  4.4 update test_whatsapp_messaging.py
  → VERIFY: pytest api/tests/ -v --tb=short
  → VERIFY: ruff check api/
```
