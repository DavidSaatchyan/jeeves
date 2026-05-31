# Phase 8: Testing & Polish

> **Date:** 2026-05-31
> **Based on:** REBRAND-MEDICAL.md (Phase 8: Days 31-33)
> **Duration:** ~3 days
> **Constraint:** `from app.main import app` must pass after every change

---

## 1. Цель

Закрыть технический долг после Phase 1-7: добавить интеграционные тесты для новой медицинской архитектуры, удалить мёртвый код (e-commerce остатки), настроить CI/CD, обновить AGENTS.md.

### Что делаем

| Область | Действие | Причина |
|---------|----------|---------|
| Dead code removal | Удалить `workers/`, `core/execution/`, `core/policies/`, `core/escalations/`, `shared/queue.py` | E-commerce остатки, не используются активными путями |
| Integration tests | CRM connectors, WhatsApp channel, Compliance, Booking flow | Критическая новая функциональность без тестов |
| CI/CD | GitHub Actions для pytest + import check | Нет автоматизации |
| AGENTS.md | Обновить правила под новую архитектуру | Документация устарела после Phase 1-7 |
| Test infrastructure | Добавить conftest fixtures для новых модулей | Необходимо для интеграционных тестов |

### Что НЕ трогаем

- Существующие тесты RAG/knowledge/chunking/WISMO — они всё ещё проходят
- `landing.html` — переписывается отдельно
- `main.py` — только если импорты мёртвого кода мешают
- `models.py` — не добавляем новые поля, только удаляем если нужно

---

## 2. Текущее состояние (AS-IS)

### Тестовая инфраструктура

| Компонент | Статус |
|-----------|--------|
| `pytest.ini` | ✅ `asyncio_mode = auto`, `testpaths = tests` |
| `conftest.py` | ✅ TestClient, auth bypass, mock_tenant, sample files |
| test_db | ✅ `test.db` на диске (SQLite) |
| Mock ChromaDB | ✅ В тестах RAG |
| Mock OpenAI | ✅ В тестах RAG |

### Существующие тесты

| Файл | Строк | Что тестирует | Статус для новой архитектуры |
|------|-------|---------------|------------------------------|
| `test_rag.py` | 386 | RAG engine (Chroma, embedding, search) | ✅ Актуально (RAG не менялся) |
| `test_rag_ext.py` | 425 | Extended RAG (product indexing) | ⚠️ `_textualize_product` — e-commerce, needs reframe |
| `test_wismo.py` | 356 | WISMO workflow (order tracking) | ❌ E-commerce мусор |
| `test_knowledge.py` | 872 | Knowledge routes + catalog upload | ⚠️ Частично актуально (catalog → services) |
| `test_catalog.py` | 825 | Catalog parser (CSV/JSON/XLSX) | ⚠️ Частично актуально (services) |
| `test_chunking.py` | 368 | Text chunking, PDF parsing | ✅ Актуально |

### Пропущенные тесты (zero coverage)

| Модуль | Риск |
|--------|------|
| `admin/` (14 файлов) | Высокий — все API endpoints без тестов |
| `core/workflows/` (appointment, marketing, followup) | Критический — ядро системы |
| `core/compliance/` | Критический — GDPR/HIPAA |
| `core/booking/` | Высокий — appointment scheduling |
| `channels/whatsapp.py` | Высокий — основной канал |
| `integrations/crm/` | Высокий — CRM адаптеры |
| `core/ai/` | Средний — LLM классификация |
| `core/communications/` | Средний — доставка сообщений |
| `core/events/` | Средний — event dispatch |
| `auth/` | Средний — JWT, tenant, регистрация |

### Мёртвый код для удаления

| Пакет | Файлов | Строк (приблизительно) |
|-------|--------|----------------------|
| `workers/` | 5 | ~120 |
| `core/execution/` | 4 | ~180 |
| `core/policies/` | 5 | ~250 |
| `core/escalations/` | 3 | ~200 |
| `shared/queue.py` | 1 | ~80 |
| **Total** | **18** | **~830** |

### CI/CD

❌ **Отсутствует полностью.** Нет GitHub Actions, нет Makefile, нет docker-compose.

---

## 3. Целевое состояние (TO-BE)

### Test Coverage Targets

| Модуль | Min Coverage | Тип тестов |
|--------|-------------|------------|
| `integrations/crm/base.py` | 90% | Unit (mocked CRM API) |
| `integrations/crm/zoho.py` | 80% | Integration (mocked HTTP) |
| `integrations/crm/hubspot.py` | 80% | Integration (mocked HTTP) |
| `integrations/crm/salesforce.py` | 80% | Integration (mocked HTTP) |
| `core/compliance/consent.py` | 95% | Unit + Integration (DB) |
| `core/compliance/audit.py` | 95% | Unit + Integration (DB) |
| `core/compliance/retention.py` | 90% | Integration (DB) |
| `core/booking/scheduler.py` | 90% | Integration (DB + locks) |
| `core/booking/slot_manager.py` | 95% | Unit |
| `core/workflows/appointment.py` | 85% | Integration (DB + state machine) |
| `core/workflows/marketing.py` | 85% | Integration (DB + state machine) |
| `core/workflows/followup.py` | 85% | Integration (DB + state machine) |
| `channels/whatsapp.py` | 70% | Integration (mocked HTTP) |
| `admin/appointments.py` | 80% | Integration (TestClient + DB) |
| `admin/compliance.py` | 80% | Integration (TestClient + DB) |
| `admin/agents.py` | 80% | Integration (TestClient + DB) |

### CI/CD Pipeline

```yaml
# .github/workflows/test.yml
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r api/requirements.txt
      - run: python -c "from app.main import app; print('Import OK')"
      - run: pytest api/tests/ -v --tb=short
```

### Dead Code — Target State

```
api/app/
├── core/
│   ├── execution/     → DELETE (4 files)
│   ├── policies/      → DELETE (5 files)
│   ├── escalations/   → DELETE (3 files)
│   └── ... (keep all others)
├── workers/           → DELETE (5 files)
├── shared/
│   ├── queue.py       → DELETE
│   └── ... (keep locks, idempotency, inbox_writer)
└── main.py            → Remove imports of deleted modules
```

---

## 4. Задачи

### 4.1. Remove Dead Code

**Описание:** Удалить 18 файлов e-commerce остатков, которые не используются активными путями.

**Файлы для удаления:**

| Путь | Причина | Зависимости |
|------|---------|-------------|
| `api/app/workers/` (весь пакет) | Background workers не задействованы | `main.py` не импортит |
| `api/app/core/execution/` (весь) | Action dispatch — unused | Никем не импортится |
| `api/app/core/policies/` (весь) | Policy engine — rebuild для medical | Никем не импортится |
| `api/app/core/escalations/` (весь) | Escalation — e-commerce specific | Никем не импортится |
| `api/app/shared/queue.py` | Unused queue | `workers/` импортит (тоже удаляем) |

**Шаги:**
1. Проверить `git grep -r "from app.workers\|from app.core.execution\|from app.core.policies\|from app.core.escalations\|from app.shared.queue"` — убедиться, что никто не импортит
2. Удалить директории: `workers/`, `core/execution/`, `core/policies/`, `core/escalations/`
3. Удалить `shared/queue.py`
4. Удалить `shared/redis/` если пуст
5. Проверить `main.py` — убрать импорты удалённых модулей
6. `python -c "from app.main import app"` — 0 errors

**Проверка:**
- `from app.main import app` — 0 ошибок
- `pytest api/tests/ -v --tb=short` — все старые тесты проходят
- Все admin UI страницы рендерятся без 500 ошибок (smoke test)

---

### 4.2. Integration Tests — CRM Connectors

**Описание:** Написать тесты для всех CRM адаптеров.

**Файлы для создания:**

| Файл | Что тестирует |
|------|---------------|
| `tests/test_crm_base.py` | Abstract connector interface, registry, error handling |
| `tests/test_crm_zoho.py` | Zoho adapter — CRUD patient, appointment, slot search |
| `tests/test_crm_hubspot.py` | HubSpot adapter — CRUD (non-PHI) |
| `tests/test_crm_salesforce.py` | Salesforce adapter — Health Cloud CRUD |
| `tests/test_crm_custom_api.py` | Custom API adapter — generic REST |
| `tests/test_crm_webhooks.py` | CRM webhook receiver |

**Test scenarios per connector:**

```python
# Core contract (all adapters must pass)
async def test_get_patient(adapter):
    patient = await adapter.get_patient("test_id")
    assert patient["id"] == "test_id"
    assert "first_name" in patient
    assert "phone" in patient

async def test_find_patient(adapter):
    patient = await adapter.find_patient(email="test@example.com")
    assert patient is not None or patient is None  # valid both ways

async def test_create_appointment(adapter):
    appt = await adapter.create_appointment(patient_id="p1", data={...})
    assert "id" in appt
    assert appt["status"] == "scheduled"

async def test_cancel_appointment(adapter):
    result = await adapter.cancel_appointment("a1")
    assert result is True

async def test_search_available_slots(adapter):
    slots = await adapter.search_available_slots(doctor_id="d1", date="2026-06-01")
    assert isinstance(slots, list)
```

**Mocking strategy:**
- Использовать `responses` (или `aioresponses` для httpx) для мока HTTP вызовов
- Каждый adapter test имеет фикстуру с мокаными ответами CRM API
- Real HTTP calls только если есть тестовый sandbox (помечено `@pytest.mark.slow`)

**Проверка:**
- `pytest tests/test_crm_*.py -v` — все тесты проходят
- Каждый adapter покрывает 4+ core scenarios
- Error handling tested (timeout, 401, 500)

---

### 4.3. Integration Tests — WhatsApp Channel

**Описание:** Написать тесты для WhatsApp channel adapter.

**Файлы для создания:**

| Файл | Что тестирует |
|------|---------------|
| `tests/test_whatsapp.py` | WhatsApp channel — send, receive, webhook, templates |
| `tests/test_whatsapp_webhook.py` | Webhook verification, message parsing, media handling |

**Test scenarios:**

```python
async def test_send_message(channel):
    result = await channel.send_message(to="+12025551234", text="Your appointment is tomorrow at 10AM")
    assert result["status"] == "sent"
    assert "message_id" in result

async def test_webhook_verification(channel):
    # Meta webhook verification (GET request with hub.challenge)
    verified = await channel.verify_webhook({"hub.mode": "subscribe", "hub.challenge": "12345"})
    assert verified == "12345"

async def test_inbound_message_parsing(channel):
    payload = {"entry": [{"changes": [{"value": {"messages": [{"from": "+12025551234", "text": {"body": "Hi"}}]}}]}]}
    messages = await channel.parse_inbound(payload)
    assert len(messages) == 1
    assert messages[0]["from"] == "+12025551234"

async def test_template_message(channel):
    result = await channel.send_template(to="+12025551234", template_name="appointment_reminder", params=["10:00 AM"])
    assert result["status"] == "sent"
```

**Mocking:**
- Мокать HTTP вызовы к Meta Graph API
- Использовать фикстуры с реальными примерами webhook payload от Meta
- Не отправлять реальные WhatsApp сообщения

**Проверка:**
- `pytest tests/test_whatsapp*.py -v` — все тесты проходят
- Webhook verification, message send, inbound parse, template send покрыты

---

### 4.4. Compliance Audit Tests

**Описание:** Написать тесты для compliance модуля — consent, audit, retention.

**Файлы для создания:**

| Файл | Что тестирует |
|------|---------------|
| `tests/test_compliance_consent.py` | ConsentManager — grant, revoke, check, expire |
| `tests/test_compliance_audit.py` | AuditLogger — record events, query, export |
| `tests/test_compliance_retention.py` | RetentionPolicy — apply, purge, settings |
| `tests/test_compliance_phi.py` | PHIMinimizer — strip, mask, tokenize |

**Test scenarios:**

```python
async def test_grant_consent(consent_manager, db):
    result = await consent_manager.grant_consent(
        patient_id="p1", consent_type="marketing", channel="whatsapp"
    )
    assert result["status"] == "granted"
    assert result["consent_type"] == "marketing"

async def test_revoke_consent(consent_manager, db):
    await consent_manager.grant_consent(...)
    result = await consent_manager.revoke_consent(patient_id="p1")
    assert result["status"] == "revoked"

async def test_check_consent_no_consent(consent_manager, db):
    result = await consent_manager.check_patient_consent(patient_id="p_new")
    assert result["has_active_consent"] is False

async def test_audit_log_record(audit_logger, db):
    event = await audit_logger.record_audit_event(
        action="phi_accessed", patient_id="p1", actor_type="staff"
    )
    assert event.id is not None

async def test_retention_apply_policy(retention, db):
    result = await retention.apply_retention_policy()
    assert "expired" in result
    assert "archived" in result

async def test_phi_minimizer():
    text = "Patient John Doe has diabetes. Call 555-0100."
    masked = await phi_minimizer.mask_phi(text)
    assert "John Doe" not in masked
    assert "555-0100" not in masked
    assert "diabetes" in masked  # clinical term kept
```

**Проверка:**
- `pytest tests/test_compliance_*.py -v` — все тесты проходят
- Consent grant + revoke + check + expiry — полный цикл
- Audit log запись, query, фильтры
- Retention policy расчёт и purge безопасны

---

### 4.5. End-to-End Test — Full Booking Flow

**Описание:** Сквозной тест полного цикла записи на приём — от поиска слота до завершения визита.

**Файл:** `tests/test_booking_e2e.py`

**Test scenario:**

```python
async def test_full_booking_flow(client, db):
    # 1. Provider creates availability slots
    slots = await slot_manager.generate_slots(provider_id="dr_smith", date="2026-06-15")
    assert len(slots) > 0

    # 2. Patient searches for available slots
    available = await slot_manager.get_available_slots(provider_id="dr_smith", date="2026-06-15")
    assert len(available) > 0

    # 3. Patient books an appointment
    appt = await scheduler.book_appointment(
        patient_id="p1", slot_id=available[0]["id"], reason="Annual checkup"
    )
    assert appt["status"] == "scheduled"
    assert appt["provider_name"] == "Dr. Smith"

    # 4. Confirm appointment
    appt = await scheduler.confirm_appointment(appt_id=appt["id"])
    assert appt["status"] == "confirmed"

    # 5. Patient arrives
    appt = await scheduler.mark_arrived(appt_id=appt["id"])
    assert appt["status"] == "arrived"

    # 6. Complete visit
    appt = await scheduler.complete_appointment(appt_id=appt["id"])
    assert appt["status"] == "completed"

    # 7. Optimistic locking — double booking prevented
    with pytest.raises(SlotAlreadyBookedError):
        await scheduler.book_appointment(patient_id="p2", slot_id=available[0]["id"])
```

**Также покрыть:**
- Cancel appointment
- Reschedule appointment
- No-show marking
- Conflict detection (double-book, overlapping times)
- Slot generation with recurring schedules

**Проверка:**
- `pytest tests/test_booking_e2e.py -v` — тест проходит
- Полный lifecycle appointment: slot → book → confirm → arrive → complete
- Race condition test (concurrent booking)

---

### 4.6. Update AGENTS.md

**Описание:** Обновить AGENTS.md в соответствии с новой архитектурой Phase 1-7.

**Изменения:**

| Секция | Действие |
|--------|----------|
| Dependency Direction | Добавить `core/booking`, `core/compliance`, `integrations/crm`, `channels/whatsapp` |
| Architecture Rules | Убрать Shopify/e-commerce references |
| Route conventions | Добавить `/admin/api/appointments`, `/admin/api/compliance` |
| Model conventions | Добавить Patient, Appointment, ConsentLog, Provider, CrmConnection |
| Channels | WhatsApp as primary (Twilio BSP), Widget as secondary |
| Testing | Добавить раздел с командой `pytest`, coverage targets |
| Dead code | Отметить что удалено (workers, execution, policies, escalations) |

**Проверка:**
- Все пути в AGENTS.md соответствуют реальной файловой структуре
- Dependency direction rules корректны
- Нет упоминаний Shopify, WISMO, e-commerce

---

### 4.7. Setup CI/CD — GitHub Actions

**Описание:** Создать минимальный CI пайплайн для автоматического тестирования.

**Файл для создания:** `.github/workflows/test.yml`

```yaml
name: Test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      redis:
        image: redis:7-alpine
        ports: ["6379:6379"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - name: Install dependencies
        run: pip install -r api/requirements.txt
      - name: Import check
        run: python -c "from app.main import app; print('Import OK')"
      - name: Run tests
        run: pytest api/tests/ -v --tb=short
      - name: Run slow tests
        run: pytest api/tests/ -v --tb=short -m "slow"
        continue-on-error: true
```

**Также добавить:** `Makefile` для локального запуска:

```makefile
.PHONY: test test-fast import-check

test:
	pytest api/tests/ -v --tb=short

test-fast:
	pytest api/tests/ -v --tb=short -m "not slow"

import-check:
	python -c "from app.main import app; print('OK')"
```

**Проверка:**
- `make import-check` — 0 ошибок
- `make test` — все тесты проходят
- GitHub Actions workflow синтаксически корректен

---

### 4.8. Clean Up Old Tests (Optional)

**Описание:** Переписать или удалить тесты, которые тестируют удалённый e-commerce код.

**Файлы:**

| Файл | Действие |
|------|----------|
| `tests/test_wismo.py` | **DELETE** — WISMO workflow удалён |
| `tests/test_rag_ext.py` | **REFACTOR** — `_textualize_product` → `_textualize_service` |
| `tests/test_knowledge.py` | **UPDATE** — catalog upload теперь services, не products |
| `tests/test_catalog.py` | **UPDATE** — parser validation для medical fields |

**Приоритет:** Низкий. Если time позволяет — сделать. В противном случае пропустить (старые тесты всё ещё проходят).

---

## 5. Порядок выполнения

| Шаг | Задача | Файлы | Проверка |
|-----|--------|-------|----------|
| 1 | Remove dead code | `workers/`, `core/execution/`, `core/policies/`, `core/escalations/`, `shared/queue.py`, `main.py` | `from app.main import app` — 0 errors |
| 2 | CRM connector tests | `tests/test_crm_*.py` | `pytest tests/test_crm_*.py -v` — pass |
| 3 | WhatsApp channel tests | `tests/test_whatsapp*.py` | `pytest tests/test_whatsapp*.py -v` — pass |
| 4 | Compliance audit tests | `tests/test_compliance_*.py` | `pytest tests/test_compliance_*.py -v` — pass |
| 5 | E2E booking flow test | `tests/test_booking_e2e.py` | `pytest tests/test_booking_e2e.py -v` — pass |
| 6 | Update AGENTS.md | `AGENTS.md` | No outdated references |
| 7 | CI/CD setup | `.github/workflows/test.yml`, `Makefile` | `make test` passes |
| 8 | Clean up old tests (optional) | `test_wismo.py`, `test_rag_ext.py`, etc. | All tests still pass |

---

## 6. Definition of Done

1. Dead code удалён: `workers/`, `core/execution/`, `core/policies/`, `core/escalations/`, `shared/queue.py` — ни одного файла не осталось
2. `from app.main import app` — 0 ошибок после удаления
3. `pytest api/tests/ -v --tb=short` — все существующие тесты проходят
4. CRM connector tests — каждый adapter (Zoho, HubSpot, Salesforce, Custom API) покрыт 4+ core scenarios
5. WhatsApp channel tests — send, receive, webhook verification, template send покрыты
6. Compliance tests — consent full lifecycle, audit log CRUD, retention apply/purge covered
7. E2E booking test — full lifecycle: slot → book → confirm → arrive → complete + optimistic locking
8. AGENTS.md — обновлён: dependency direction, architecture rules, model conventions, testing section
9. CI/CD — GitHub Actions workflow создан, `make test` работает
10. Весь Phase 8 в одном коммите с сообщением `test: add integration tests + remove dead code + setup CI`

---

## 7. Структура файлов после Phase 8

```
api/
├── app/
│   ├── core/
│   │   ├── ai/              # KEEP
│   │   ├── booking/         # KEEP
│   │   ├── communications/  # KEEP
│   │   ├── compliance/      # KEEP
│   │   ├── events/          # KEEP
│   │   ├── timeline/        # KEEP
│   │   ├── workflows/       # KEEP
│   │   ├── memory.py        # KEEP
│   │   ├── execution/       # ❌ DELETED
│   │   ├── policies/        # ❌ DELETED
│   │   └── escalations/     # ❌ DELETED
│   ├── workers/             # ❌ DELETED
│   ├── shared/
│   │   ├── inbox_writer.py  # KEEP
│   │   ├── locks.py         # KEEP
│   │   ├── idempotency.py   # KEEP
│   │   └── queue.py         # ❌ DELETED
│   └── ... (unchanged)
├── tests/
│   ├── __init__.py          # KEEP
│   ├── conftest.py          # UPDATE — add CRM, WhatsApp, compliance fixtures
│   ├── test_rag.py          # KEEP
│   ├── test_rag_ext.py      # REFACTOR (optional)
│   ├── test_knowledge.py    # UPDATE (optional)
│   ├── test_catalog.py      # UPDATE (optional)
│   ├── test_chunking.py     # KEEP
│   ├── test_wismo.py        # ❌ DELETE
│   ├── test_crm_base.py     # NEW
│   ├── test_crm_zoho.py     # NEW
│   ├── test_crm_hubspot.py  # NEW
│   ├── test_crm_salesforce.py # NEW
│   ├── test_crm_custom_api.py # NEW
│   ├── test_crm_webhooks.py # NEW
│   ├── test_whatsapp.py     # NEW
│   ├── test_whatsapp_webhook.py # NEW
│   ├── test_compliance_consent.py # NEW
│   ├── test_compliance_audit.py # NEW
│   ├── test_compliance_retention.py # NEW
│   ├── test_compliance_phi.py # NEW
│   └── test_booking_e2e.py  # NEW
├── .github/workflows/
│   └── test.yml             # NEW
├── Makefile                  # NEW
├── pytest.ini               # KEEP
└── requirements.txt         # UPDATE — add responses, aioresponses
```

---

## 8. Risky

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| Dead code removal ломает импорты | Средняя | `git grep` перед удалением; `python -c "from app.main import app"` после каждого шага |
| CRM тесты требуют реальные API ключи | Высокая | Все тесты используют моки (responses/aioresponses). `@pytest.mark.slow` для real API тестов |
| WhatsApp webhook тесты — сложный payload | Средняя | Использовать реальные примеры Meta webhook payload как фикстуры |
| Booking E2E тест зависит от БД | Средняя | Использовать SQLite test.db + транзакционный rollback |
| Старые тесты (WISMO) падают после удаления кода | Низкая | Удалить `test_wismo.py` вместе с WISMO кодом |
| Нет опыта с CI/CD в проекте | Низкая | Базовый GitHub Actions workflow — копировать из документации |
