# MVP: Pabau — Единственная интеграция (EU-only)

## Почему

Pabau — all-in-one платформа для клиник (3,000+ практик). В одном продукте:
- **EMR / Patient management** — клиенты, медкарты, формы, согласия
- **Scheduling** — календарь, онлайн-запись, слоты, напоминания
- **Invoicing / Payments** — счета, Stripe, Xero
- **Marketing CRM** — кампании, Email/SMS, воронки, loyalty
- **GDPR-compliant** — сервера в EU (Великобритания)

**Всё остальное — не нужно.** Ни Zoho, ни Google Calendar, ни NexHealth, ни Meetergo.

---

## Что делаем: удаляем всё лишнее

| Компонент | Действие | Строк |
|-----------|----------|-------|
| `integrations/crm/zoho.py` | 🗑️ удалить | ~200 |
| `integrations/crm/custom_api.py` | 🗑️ удалить | ~50 |
| `integrations/crm/base.py` | 🗑️ удалить | ~70 |
| `integrations/crm/exceptions.py` | 🗑️ удалить | ~50 |
| `integrations/crm/webhooks.py` | 🗑️ удалить | ~215 |
| `integrations/credentials.py` | 🗑️ удалить | ~69 |
| `core/calendar/google.py` | 🗑️ удалить | ~265 |
| `core/calendar/nexhealth.py` | 🗑️ удалить | ~200+ (уже написан) |
| `core/calendar/meetergo.py` | 🗑️ удалить | ~200+ (уже написан) |
| `core/calendar/` (package) | 🗑️ удалить | всё |
| `admin/calendar.py` | 🗑️ удалить | ~173 |
| `admin/integrations.py` | 🗑️ удалить | ~346 |
| `models.py` — CrmConnection | 🗑️ удалить модель | |
| `models.py` — NativeConnector | 🗑️ удалить модель | |
| `models.py` — CalendarConnection | 🗑️ удалить модель | |
| **Tests**: `test_crm_*.py` (6 files) | 🗑️ удалить | ~500 |
| **Tests**: `test_calendar_*.py` (2 files) | 🗑️ удалить | ~300 |
| Alembic migrations (calendar_connections) | 🗑️ откатить/оставить | — |

## Что добавляем: один коннектор

```
NEW: api/app/integrations/pabau.py           — PabauConnector (AbstractCrmConnector)
NEW: api/tests/test_pabau.py                 — 15-20 тестов
NEW: api/app/admin/pabau.py                  — админ-панель для Pabau
NEW: api/app/templates/pabau_connections.html — UI подключения
```

## Финальная структура

```
api/app/
├── core/
│   ├── booking/             — остаётся (работает через CRM → Pabau)
│   │   ├── __init__.py       — упростить: только Pabau
│   │   ├── slot_manager.py   — остаётся (генерация слотов)
│   │   └── scheduler.py      — остаётся (ошибки)
│   └── ... (compliance, ai, workflows — не трогаем)
├── integrations/
│   └── pabau.py              — ЕДИНСТВЕННЫЙ коннектор
├── admin/
│   └── pabau.py              — админка для подключения Pabau
├── templates/
│   └── pabau_connections.html
├── models.py                  — только Patient, Provider, AppointmentCache, остальное
├── config.py                  — только Pabau API key
└── main.py                    — убрать лишние роутеры
```

## PabauConnector

`AbstractCrmConnector` остаётся как интерфейс (но можно и его удалить, если будет Pabau-only).

| Метод | Pabau API | Статус |
|-------|-----------|--------|
| `get_patient(id)` | `GET /patients/{id}` | ✅ |
| `find_patient(email/phone)` | `GET /patients?search=` | ✅ |
| `create_patient(data)` | `POST /patients` | ✅ |
| `update_patient(id, data)` | `PATCH /patients/{id}` | ✅ |
| `create_appointment(...)` | `POST /appointments` | ✅ |
| `cancel_appointment(id)` | `DELETE /appointments/{id}` | ✅ |
| `update_appointment(id, data)` | `PATCH /appointments/{id}` | ✅ |
| `search_available_slots(...)` | fallback: slot generator | ⚠️ |
| `get_appointment(id)` | `GET /appointments/{id}` | ✅ |
| `list_appointments(...)` | `GET /appointments` | ✅ |
| `get_patient_appointments(id)` | `GET /appointments?patient_id=X` | ✅ |
| `verify_webhook_signature(...)` | HMAC check | ✅ |
| `parse_webhook_event(...)` | JSON → canon | ✅ |

## Booking Engine (упрощение)

Текущий `core/booking/__init__.py`:
```python
# 1. Try CRM → 2. Try Calendar → 3. Error
```

Новый:
```python
# 1. Try Pabau (единственный CRM) → 2. Error
```

Убираем логику "CRM-first → Calendar-fallback". Только Pabau.

## Milestones

| Шаг | Что | Время |
|-----|-----|-------|
| 1 | Удалить всё лишнее: Zoho, Google Calendar, Custom API, admin/integrations.py, admin/calendar.py, models (Crm/Calendar/Native), тесты | 1h |
| 2 | Очистить booking engine от calendar fallback | 20min |
| 3 | Создать PabauConnector с полным CRUD | 2h |
| 4 | Создать admin/pabau.py + pabau_connections.html | 30min |
| 5 | Обновить main.py, config.py, models.py | 20min |
| 6 | Написать тесты | 1h |
| 7 | `python -c "from app.main import app"` + `pytest` + `ruff` | 10min |

## Файлы

```
REMOVED (18+ files):
  api/app/integrations/crm/*                    — весь пакет (6 файлов, ~700 строк)
  api/app/integrations/credentials.py           — убрать (69 строк)
  api/app/core/calendar/*                       — весь пакет (4 файла, ~700 строк)
  api/app/admin/calendar.py                     — убрать (173 строки)
  api/app/admin/integrations.py                 — убрать (346 строк)
  api/app/templates/connections.html            — убрать (389 строк)
  api/tests/test_crm_*.py                       — 6 файлов (~500 строк)
  api/tests/test_calendar_*.py                  — 2 файла (~300 строк)

NEW (3 files):
  api/app/integrations/pabau.py                 — +~180 строк
  api/app/admin/pabau.py                        — +~60 строк
  api/app/templates/pabau_connections.html      — +~100 строк
  api/tests/test_pabau.py                       — +~180 строк

MODIFIED (3 files):
  api/app/core/booking/__init__.py              — упростить
  api/app/models.py                             — удалить лишние модели
  api/app/config.py                             — pabau_api_key
  api/app/main.py                               — убрать лишние роутеры
  api/app/integrations/crm/__init__.py          — переписать (pabau-only)
```
