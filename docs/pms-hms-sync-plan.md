# PMS→HMS Sync: Implementation Plan

Based on `docs/pms-hms-sync-analysis.md` v2. All priorities, dependencies, and risks are documented.

---

> **⚠️ Критические баги, найденные при code review плана (06.06.2026):**
> 1. `poll_crm_changes()` вызывает `get_crm_adapter_for_tenant(tenant.id)` — функция ждёт `Tenant`, не `UUID`. Упадёт с `AttributeError`. Пофиксено в 0.1.
> 2. Ошибки sync (например, Cliniko timeout) нигде не сохраняются — `_save_sync_result()` пишет только успешные типы. После редиректа пользователь не видит ошибку. Пофиксено в 0.3.
> 3. `reindex_from_sql` хардкодит имена колонок (`price_cents`, `duration_minutes`) и сломается, если schema `raw_data` изменится при рефакторинге Phase 1. Добавлен check в 1.7.
> 4. Нет тестов для HmsConnector. Добавлена задача 1.8.
> 5. Нет rollback-стратегии. Добавлена задача 1.9 (feature flag).

---

## Phase 0: Quick Wins (P0 UX)

### 0.0 Fix existing bug in poll_crm_changes

**Файлы:** `api/app/core/crm_sync.py`

**Баги:** `line 54 — get_crm_adapter_for_tenant(tenant.id)` принимает `Tenant`, не `UUID`.

**Что сделать:**
```python
# Было (падает с AttributeError):
adapter = get_crm_adapter_for_tenant(tenant.id)

# Стало:
adapter = get_crm_adapter_for_tenant(tenant)
```

**Проверка:**
- `poll_crm_changes(str(tenant.id))` не падает с `AttributeError: 'UUID' object has no attribute 'crm_config'`
- `pytest api/tests/ -v --tb=short` — тесты проходят

**Оценка:** 5 мин

---

### 0.1 Auto-first-sync after CRM connect

**Файлы:** `api/app/admin/integrations_hub.py`, `api/app/core/crm_sync.py`

**Что сделать:**
- Импортировать `BackgroundTasks` из `fastapi`
- Добавить `background_tasks: BackgroundTasks` в `configure_crm()`
- После `db.commit()` → `background_tasks.add_task(poll_crm_changes, tenant.id)`
- `poll_crm_changes` принимает `str | UUID` — передаём `str(tenant.id)` (сериализуемо для BackgroundTasks)
- Добавить `logger.info("Auto-sync after CRM configure: enqueued for tenant %s", tenant.id)` в `configure_crm`

**Проверка:**
- POST /admin/api/integrations/crm/configure → ответ 200
- Через 2-5 сек GET /knowledge/sync/crm/status → `last_sync_at` заполнен, count > 0
- Лог: `"Auto-sync after CRM configure: enqueued for tenant <uuid>"`

**Риски:**
- slow sync (1000+ services) → BackgroundTasks умрёт при рестарте worker. Для MVP ок.
- tenant.crm_config уже закоммичен перед background task — ок.

**Оценка:** 30 мин

---

### 0.2 Show error text in sync cards

**Файлы:** `api/app/templates/knowledge.html` (JS + HTML)

**Зависимости:** 0.3 (ошибки должны сохраняться)

**Что сделать:**
- `GET /knowledge/sync/crm/status` уже возвращает sync_counts с `last_sync`
- Добавить в ответ поле `errors: {services: [...], practitioners: [...], clinic: [...]}` (из `tenant.crm_config["sync_errors"]`)
- В `renderCard()` при `state === 'error'` показывать текст: `pmsDetail.textContent = errorText`
- Сделать ошибку кликабельной (развернуть detail)

**Проверка:**
- При ошибке sync → красный крестик + текст ошибки под заголовком
- Клик по ошибке → полный traceback (опционально)

**Оценка:** 1 ч

---

### 0.3 Persist sync errors in crm_config

**Файлы:** `api/app/core/crm_sync.py`, `api/app/knowledge/sync.py`

**Предусловие:** `_save_sync_result()` не сохраняет ошибки. Если sync упал, `result["services"]["errors"]` не пишется в `tenant.crm_config`.

**Что сделать:**
```python
# В _save_sync_result() и sync_crm():
config["sync_errors"] = {}
for type_key in ("services", "practitioners", "clinic"):
    if type_key in result and result[type_key].get("errors"):
        config["sync_errors"][type_key] = result[type_key]["errors"][:500]
# Очищать при успешном sync
```

**Проверка:**
- После ошибки sync → `tenant.crm_config["sync_errors"]["services"]` содержит текст
- После успешного sync → `sync_errors` пуст

**Оценка:** 30 мин

---

## Phase 1: HmsConnector Interface

### 1.1 Create HmsConnector base class

**Файлы:** `api/app/integrations/hms.py` (new file)

**Что сделать:**
```python
class HmsConnector(ABC):
    provider: str

    @abstractmethod
    def fetch_services(self, updated_since: str | None = None) -> list[dict]: ...
    @abstractmethod
    def fetch_practitioners(self) -> list[dict]: ...
    @abstractmethod
    def fetch_clinics(self) -> list[dict]: ...
    @abstractmethod
    def test_connection(self) -> bool: ...
```

**Проверка:** `python -c "from app.integrations.hms import HmsConnector"` — ok

**Оценка:** 30 мин

---

### 1.2 ClinikoConnector → HmsConnector

**Файлы:** `api/app/integrations/cliniko.py`

**Что сделать:**
- ClinikoConnector наследует `(AbstractCrmConnector, HmsConnector)`
- Реализовать `fetch_services()` — обёртка над `get_billable_items("Service")` + `get_appointment_types()` + `get_appointment_type_billable_items()` + `enrich_services_with_descriptions()`
- Реализовать `fetch_practitioners()` — обёртка над `get_practitioners()`
- Реализовать `fetch_clinics()` — обёртка над `get_businesses()`
- `fetch_*` возвращают `list[dict]` с сырыми данными HMS (как сейчас)

**Проверка:**
```python
from app.integrations.cliniko import ClinikoConnector
c = ClinikoConnector({"api_key": "...", "shard": "au1"})
assert len(c.fetch_services()) > 0
assert len(c.fetch_practitioners()) > 0
```

**Зависимости:** 1.1

**Оценка:** 1.5 ч

---

### 1.3 PabauConnector → HmsConnector

**Файлы:** `api/app/integrations/pabau.py`

**Что сделать:**
- PabauConnector наследует `(AbstractCrmConnector, HmsConnector)`
- `fetch_services()` → `get_services()`
- `fetch_practitioners()` → `get_practitioners()`
- `fetch_clinics()` → `return []` (заглушка, как сейчас `get_businesses()`)

**Проверка:** Аналогично 1.2

**Зависимости:** 1.1

**Оценка:** 30 мин

---

### 1.4 Update resolver

**Файлы:** `api/app/integrations/resolver.py`

**Что сделать:**
- Добавить `get_hms_adapter_for_tenant()` — возвращает `HmsConnector`, а не `AbstractCrmConnector`
- Или переиспользовать `get_crm_adapter_for_tenant()` — он уже возвращает объект, который имплементирует оба интерфейса

**Проверка:**
```python
adapter = get_hms_adapter_for_tenant(tenant)
assert isinstance(adapter, HmsConnector)
```

**Зависимости:** 1.2, 1.3

**Оценка:** 30 мин

---

### 1.5 Refactor sync engine

**Файлы:** `api/app/core/crm_sync.py`, `api/app/knowledge/sync.py`

**Что сделать:**
- В `poll_crm_changes()` и `sync_crm()` использовать `HmsConnector` вместо прямых вызовов `adapter.get_billable_items()`, `adapter.get_practitioners()`, `adapter.get_businesses()`
- `enrich_services_with_descriptions` оставить внутри ClinikoConnector.fetch_services()

**Проверка:**
- `POST /knowledge/sync/crm` → те же результаты, что и до рефакторинга
- `pytest api/tests/ -v --tb=short` — все тесты проходят

**Зависимости:** 1.4

**Риски:**
- Нужно быть осторожным с enrich_services_with_descriptions — не потерять при рефакторинге
- `updated_since` для инкрементального sync — проверить, что фильтр работает одинаково

**Оценка:** 2 ч

---

### 1.6 Update field mappers

**Файлы:** `api/app/shared/pms_fields.py`

**Что сделать:**
- `service_fields()`, `practitioner_fields()`, `clinic_fields()` оставить как есть
- Никаких изменений схемы данных — только рефакторинг вызовов

**Проверка:** `pytest api/tests/test_pms_fields.py -v`

**Зависимости:** 1.5

**Оценка:** 15 мин

---

### 1.7 Protect reindex_from_sql against raw_data schema changes

**Файлы:** `api/app/knowledge/sync.py`

**Критичность:** 🔴 После Phase 1 raw_data может изменить структуру (например, `price_cents` → `price`). `reindex_crm_from_sql()` хардкодит колонки (`sync.py:127-130`) и сломается.

**Что сделать:**
- Вынести построение `items` в `reindex_crm_from_sql()` в отдельные функции-хелперы, которые читают из field mappers
- Или хотя бы `try/except` с падением на отсутствующую колонку + логирование

**Проверка:** `POST /knowledge/sync/crm/reindex` работает после изменения field mapper'а

**Зависимости:** 1.5

**Оценка:** 1 ч

---

### 1.8 Update tests for HmsConnector

**Файлы:** `api/tests/test_admin_cliniko.py`, `api/tests/test_pms_fields.py`

**Что сделать:**
- Заменить моки `get_billable_items()` → `fetch_services()` в тестах
- Проверить, что `ClinikoConnector` имплементирует `HmsConnector`
- `test_connector_interface()` — что `isinstance(cliniko_connector, HmsConnector)`

**Проверка:** `pytest api/tests/ -v --tb=short` — все проходят

**Зависимости:** 1.2, 1.3

**Оценка:** 1.5 ч

---

### 1.9 Feature flag for HmsConnector rollback

**Файлы:** `api/app/config.py`, `api/app/core/crm_sync.py`, `api/app/knowledge/sync.py`

**Что сделать:**
- Добавить `FEATURE_USE_HMS_CONNECTOR: bool = True` в `Settings`
- ENV var `FEATURE_USE_HMS_CONNECTOR` (default: true)
- В `poll_crm_changes()` и `sync_crm()`:
  ```python
  if settings.FEATURE_USE_HMS_CONNECTOR:
      adapter = get_hms_adapter_for_tenant(tenant)
  else:
      adapter = get_crm_adapter_for_tenant(tenant)
  ```

**Проверка:**
- `FEATURE_USE_HMS_CONNECTOR=false` → sync работает через старый `AbstractCrmConnector`
- `FEATURE_USE_HMS_CONNECTOR=true` → sync работает через `HmsConnector`

**Зависимости:** 1.5

**Оценка:** 30 мин

---

## Phase 2: Schema Validation for raw_data

### 2.1 Create field schema registry

**Файлы:** `api/app/shared/hms_schemas.py` (new file), `api/app/config.yaml` (опционально)

**Что сделать:**
```python
HMS_FIELD_SCHEMAS: dict[str, dict[str, Any]] = {
    "cliniko": {
        "service": {"name": "text", "description": "text", "price": "int", ...},
        "practitioner": {"display_name": "text", "title": "text", ...},
        "clinic": {"business_name": "text", "address": "text", ...},
    },
    "pabau": {
        "service": {"name": "text", ...},
        "practitioner": {"display_name": "text", ...},
        "clinic": {},  # not supported
    },
}
```

**Проверка:** Импорт без ошибок

**Оценка:** 30 мин

---

### 2.2 Add validation in sync pipeline

**Файлы:** `api/app/core/crm_sync.py`, `api/app/shared/hms_schemas.py`

**Что сделать:**
- Перед `upsert_objects()` проверять raw_data по схеме
- Логировать warning при несоответствии: `logger.warning("Field %s missing in %s %s", field, provider, entity_type)`
- Не блокировать sync — только log + metric

**Проверка:**
- Sync с Cliniko → лог "Field price missing in cliniko service X" (если поле отсутствует)
- Тест: подставить record без обязательного поля → warning, не ошибка

**Зависимости:** 2.1

**Оценка:** 1 ч

---

## Phase 3: UX Improvements (P1)

### 3.1 Diff indicator (+N new / unchanged)

**Файлы:** `api/app/core/crm_sync.py`, `api/app/templates/knowledge.html`

**Что сделать:**
- После sync сохранять snapshot counts: `tenant.crm_config["last_counts"] = {...}`
- В `GET /knowledge/sync/crm/status` добавить `diff: {services: 3, practitioners: 0, clinic: 0}`
- В renderCard показывать "+3 new" или "unchanged"

**Проверка:**
- Первый sync → "+3 new" (так как было 0)
- Второй sync (без изменений) → "unchanged"
- Третий sync (с новыми данными) → "+2 new"

**Зависимости:** Нет (чисто API + frontend)

**Оценка:** 2 ч

---

### 3.2 Preview synced data

**Файлы:** `api/app/templates/knowledge.html`, `api/app/knowledge/__init__.py` (or `sync.py`)

**Что сделать:**
- Добавить API endpoint: `GET /knowledge/sync/crm/{type}` — возвращает список записей (name, description, last_updated)
- По клику на карточку → открыть modal со списком
- Для service: name + price + duration
- Для practitioner: name + designation + active
- Для clinic: name + address + phone

**Проверка:**
- Клик по карточке Services → modal с 42 строками
- Клик по карточке Practitioners → modal с 5 строками

**Зависимости:** Нет

**Оценка:** 3 ч

---

### 3.3 Onboarding tooltip for new users

**Файлы:** `api/app/templates/knowledge.html`

**Что сделать:**
- При первом подключении Cliniko показать tooltip/баннер:
  "🎉 Cliniko connected! Your practice data is being synced. This may take up to 2 minutes."
- Скрывать после первого sync или клика

**Проверка:**
- После connect → баннер виден
- После syncAll → баннер скрыт

**Зависимости:** 0.1

**Оценка:** 1 ч

---

## Phase 4: Postponed / Optional

### 4.1 PMS→HMS rename

**Когда делать:** При следующем breaking change (новая таблица, новая миграция)

**Что сделать:**
- `ALTER TABLE pms_services RENAME TO hms_services` (и т.д.)
- `PmsService` → `HmsService` в models.py
- `shared/pms_fields.py` → `shared/hms_fields.py`
- Все импорты
- Обновить константы в Chroma (`source: "pms"` → `source: "hms"`)

**Риски:**
- ACCESS EXCLUSIVE LOCK на время rename
- Нужен zero-downtime подход (или окно обслуживания)

---

### 4.2 Cliniko webhook verification

**Когда делать:** При наличии тестового Cliniko аккаунта

**Что сделать:**
- Проверить, отправляет ли Cliniko реально webhooks (настройка Settings → Integrations → Webhooks)
- Если нет — удалить `cliniko_webhook` route и `verify_webhook_signature`
- Если да — задокументировать события

---

### 4.3 Progress bar for sync

**Когда делать:** Когда sync начнёт занимать >30 сек (сейчас быстрее)

---

## Milestones & Dependencies

```
Fix        Phase 0           Phase 1                 Phase 2       Phase 3
───        ───────           ───────                 ───────       ───────
0.0 ─┐     0.1 ─┐            1.1 ─┐                  2.1 ─┐        3.1 ┐
     │           │            │                          │            │
     │     0.3 ──┤            1.2 ┼─ 1.4 ─ 1.5 ─ 1.7 ──┤   2.2 ─────┤  3.2 ┐
     │           │            │     │        │          │            │      │
     │     0.2 ──┘            1.3 ┘        1.8 ────────┘          3.3 ────┘
     │                                   1.9 ────────┘
     └──────┘
```

| Milestone | Tasks | Время | Можно деплоить? |
|-----------|-------|-------|-----------------|
| M0 | 0.0, 0.1, 0.2, 0.3 | 2 ч | ✅ Без риска |
| M1 | 1.1–1.9 | 8.5 ч | ✅ С feature flag rollback |
| M2 | 2.1, 2.2 | 1.5 ч | ✅ Только логи |
| M3 | 3.1–3.3 | 6 ч | ✅ Только frontend |
| M4 | 4.1 | TBD | ❌ Риск locking |

---

## Total Estimate

| Phase | Tasks | Hours |
|-------|-------|-------|
| Fix | 0.0 | 0.1 |
| Phase 0 | 0.1, 0.2, 0.3 | 2 |
| Phase 1 | 1.1–1.9 | 8.5 |
| Phase 2 | 2.1, 2.2 | 1.5 |
| Phase 3 | 3.1–3.3 | 6 |
| **Total** | **15 tasks** | **18 ч** |
