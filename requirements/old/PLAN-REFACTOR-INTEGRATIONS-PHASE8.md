# Phase 8: CRM Strategy — Remove HubSpot/Salesforce, Add NexHealth/meetergo

## Why

| Connector | Lines | PHI-safe | Appointment API | BAA on chat | Tests | Вердикт |
|-----------|-------|----------|----------------|-------------|-------|---------|
| Zoho      | ~200  | ✅       | ✅ полный      | ✅          | 27    | ✅ Оставить |
| HubSpot   | 105   | ❌       | ⚠️ частичный   | ❌          | 24    | 🗑️ Удалить |
| Salesforce| 68    | ✅(stub) | ❌ 100% stubs  | N/A         | 0     | 🗑️ Удалить |

**HubSpot**: BAA не покрывает чаты/WhatsApp — значит Jeeves не может через него общаться с пациентами.
`phi_safe = False`, 40% кода — заглушки. Единственное, что работает — не-PHI контакты. Бесполезен.

**Salesforce**: 68 строк чисто заглушек ("Not implemented in Phase 3"). $350-500/user/month.
Менее 1% клиник его используют. Для target market (SMB) — не нужен.

**Zoho**: $14-52/user/month, BAA, Healthcare CRM module, privacy-first.
Connector полностью работает. #2 в SMB-сегменте (12.4%). Основной CRM-бекенд.

---

## Scope of Changes

### Phase 8.1 — Remove HubSpot (estimated: 1h)
```
REMOVE:
  api/app/integrations/crm/hubspot.py        (105 lines — весь файл)
  api/tests/test_crm_hubspot.py              (184 lines — 24 tests)

MODIFY:
  api/app/integrations/crm/__init__.py       — убрать try/except импорт HubSpotAdapter
  api/app/admin/integrations.py              — убрать hubspot из _CONNECTOR_FIELDS, _WEBHOOK_EVENTS
  api/app/templates/connections.html          — убрать HubSpot PROVIDERS tab
```

После удаления: `python -c "from app.main import app"` + `pytest` — must pass.

### Phase 8.2 — Remove Salesforce (estimated: 30min)
```
REMOVE:
  api/app/integrations/crm/salesforce.py     (68 lines — 100% stubs)

MODIFY:
  api/app/integrations/crm/__init__.py       — убрать try/except импорт SalesforceAdapter
  (в connections.html Salesforce таба нет — UI не трогаем)
```

После удаления: `python -c "from app.main import app"` + `pytest` — must pass.

### Phase 8.3 — Zoho как primary CRM (estimated: 1h)
```
MODIFY:
  api/app/core/booking/__init__.py            — приоритет Zoho в booking engine
  api/app/admin/integrations.py              — Zoho первый в списке _CONNECTOR_FIELDS
  api/app/templates/connections.html         — Zoho первый таб (уже, но проверить)
  api/app/integrations/crm/__init__.py       — register_crm_provider("zoho") первой
```

Проверить, что connector покрывает всё, что нужно для booking engine:
- `create_appointment` ✅
- `cancel_appointment` ✅
- `update_appointment` ✅  
- `search_available_slots` ✅
- `get_patient_appointments` ✅
- `get_appointment` ✅
- `list_appointments` ✅
- webhook signature verification ✅

### Phase 8.4 — NexHealth Calendar Provider (estimated: 3h)
```
NEW FILES:
  api/app/core/calendar/nexhealth.py         — NexHealthProvider(AbstractCalendarProvider)
  api/tests/test_calendar_nexhealth.py       — 10-15 tests

MODIFY:
  api/app/core/calendar/__init__.py           — register nexhealth в get_calendar_provider()
  api/app/models.py                           — CalendarConnection: provider="nexhealth"
  api/app/admin/integrations.py               — добавить в _CONNECTOR_FIELDS["nexhealth"]
  api/app/templates/connections.html          — добавить NexHealth в PROVIDERS + calendar panels
  api/requirements.txt                        — httpx (если нет)
```

NexHealth API endpoints:
```
GET  /appointment_slots?provider=X&date=Y   → слоты
POST /appointments                          → создать запись
PATCH /appointments/:id                     → подтвердить/отменить
GET  /patients                              → получить пациента
```

Webhooks: appointment.created, appointment.cancelled, appointment.updated

### Phase 8.5 — Meetergo Calendar Provider (estimated: 3h)
```
NEW FILES:
  api/app/core/calendar/meetergo.py          — MeetergoProvider(AbstractCalendarProvider)
  api/tests/test_calendar_meetergo.py        — 10-15 tests

MODIFY:
  api/app/core/calendar/__init__.py           — register meetergo в get_calendar_provider()
  api/app/models.py                           — CalendarConnection: provider="meetergo"
  api/app/admin/integrations.py               — добавить в _CONNECTOR_FIELDS["meetergo"]
  api/app/templates/connections.html          — добавить Meetergo в PROVIDERS + calendar panels
```

Meetergo API v4 endpoints:
```
GET  /v4/booking-availability?meetingTypeId=X&start=Y&end=Z   → слоты
POST /v4/booking                                                → создать запись
POST /v4/appointment/:id/cancel                                 → отмена
POST /v4/appointment/:id/reschedule                             → перенос
GET  /v4/appointment/paginated                                  → список записей
```

Webhooks (Enterprise): booking_created, booking_rescheduled, booking_cancelled

### Phase 8.6 — Update Booking Engine (estimated: 1h)
```
MODIFY:
  api/app/core/booking/__init__.py     — booking engine выбирает правильный backend:
    1. Если есть Zoho → Zoho (create_appointment)
    2. Если есть NexHealth → NexHealth
    3. Если есть meetergo → meetergo
    4. Если есть Google Calendar → Google
    5. Если ничего нет → ошибка

  api/app/core/booking/slot_manager.py — get_available_slots() аналогично:
    1. Zoho search_available_slots
    2. NexHealth get_available_slots  
    3. meetergo get_available_slots
    4. Google Calendar get_available_slots
    5. empty list
```

### Phase 8.7 — Config Updates (estimated: 30min)
```
MODIFY:
  api/app/config.py       — добавить NEXHEALTH_API_KEY, NEXHEALTH_SUBDOMAIN
                            MEETERGO_API_KEY (опционально, для Platform API)
  api/.env.example        — примеры переменных
```

---

## Test Strategy

| Что тестируем | Подход |
|--------------|--------|
| Удаление HubSpot/Salesforce | `pytest` — 184 строк тестов уходят, остальные должны пройти |
| NexHealthProvider | Mock HTTP → test slots, book, cancel, error handling |
| MeetergoProvider | Mock HTTP → test slots, book, cancel, reschedule, error handling |
| Booking engine priority | Zoho first → NexHealth → meetergo → Google → error |
| Regression | 436 existing tests + новые = 450+ |

---

## Migration / Rollback

**Удаление HubSpot и Salesforce** — необратимо (удаление файлов).
Но: код хранится в git. Если понадобится — `git checkout <old-commit> -- api/app/integrations/crm/hubspot.py`.

**NexHealth/meetergo** — новые файлы, добавление без удаления существующего. 
Безопасно: Google Calendar остаётся как fallback.

---

## Dependencies

```
Новые зависимости:
  httpx                          (уже есть в requirements.txt)
  
NexHealth:
  API key (Bearer token)
  Subdomain + Location ID

Meetergo (Enterprise план):
  Platform API Key (ak_live:*)
  x-meetergo-api-user-id
```

---

## File Change Summary

```
REMOVED (2 files):
  api/app/integrations/crm/hubspot.py        -105 lines
  api/app/integrations/crm/salesforce.py      -68 lines
  api/tests/test_crm_hubspot.py               -184 lines, 24 tests

NEW (4 files):
  api/app/core/calendar/nexhealth.py          +~150 lines
  api/app/core/calendar/meetergo.py           +~150 lines
  api/tests/test_calendar_nexhealth.py        +~200 lines, 10-15 tests
  api/tests/test_calendar_meetergo.py         +~200 lines, 10-15 tests

MODIFIED (7 files):
  api/app/integrations/crm/__init__.py
  api/app/core/calendar/__init__.py
  api/app/core/booking/__init__.py
  api/app/core/booking/slot_manager.py
  api/app/admin/integrations.py
  api/app/templates/connections.html
  api/app/config.py

TOTAL: ~1250 lines added, ~357 removed, ~7 files modified
```
