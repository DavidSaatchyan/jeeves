# План удаления Appointment UI

## Цель
Удалить **только UI-слой** Appointment Manager из админ-панели.  
Вся backend-логика (Workflow, Booking Engine, AppointmentCache, AI intents, CRM adapters, Calendar provider) **остаётся**.

---

## Что ОСТАЁТСЯ (агент продолжает работать)

| Компонент | Роль |
|-----------|------|
| `core/workflows/appointment.py` | State machine — диалог с пациентом (выбор слота, подтверждение, напоминание, no-show) |
| `core/booking/__init__.py` | `book_appointment()` / `cancel_appointment()` / `reschedule_appointment()` |
| `core/booking/slot_manager.py` | `get_available_slots()` / `generate_slots()` |
| `core/booking/scheduler.py` | `SlotAlreadyBookedError`, `AppointmentNotFoundError` |
| `core/booking/calendar_sync.py` | Push/pull заглушки |
| `AppointmentCache` (models.py) | Операционный кэш (флаги напоминаний, статус синхронизации) |
| `core/ai/intent_classifier.py` | Intent = "appointment", "reschedule", "cancel" |
| `core/ai/triage.py` | Параметры записи из сообщения |
| `integrations/crm/base.py` | Abstract methods create/cancel/update/list appointment |
| `integrations/crm/zoho.py` | CRUD в Zoho Appointments__s |
| `integrations/crm/hubspot.py` | create_appointment → MEETING |
| `integrations/crm/custom_api.py` | CRUD через Custom API |
| `integrations/crm/webhooks.py` | Синхронизация AppointmentCache из вебхуков |
| `core/calendar/` | Google Calendar provider |
| `channels/whatsapp.py` | Routing appointment intent → workflow |
| `core/events/schemas.py` | `appointment_requested` event type |
| `core/workflows/marketing.py` | `APPOINTMENT_BOOKED` state |

---

## Что УДАЛЯЕТСЯ (только UI)

### Phase A — `agents.html` (таб Appointment Manager)

**A1** — Удалить tab-кнопку "Appointment Manager" (строки ~92-96):
```html
<button class="ch-tab active" data-agent="appointment" onclick="selectAgent('appointment')">
  <span class="ch-tab-icon">...</span>
  Appointment Manager
  <span class="ch-tab-badge" ... id="count-appointment">0</span>
</button>
```

**A2** — Удалить entry `{id: 'appointment', ...}` из массива `AGENTS` (строки ~117-123).  
Убирается список состояний `AWAITING_INTENT, CHECKING_SCHEDULE, OFFERING_SLOTS, ...`

**A3** — Сменить `currentAgent` по умолчанию с `'appointment'` на `'marketing'` в 3 местах (строки ~140, 251, 258).

**A4** — Убрать `'appointment'` из массива в цикле обновления badge (строка ~242):
```js
['appointment','marketing','followup'] → ['marketing','followup']
```

### Phase B — `base.html` (сайдбар)

**B1** — Удалить нав-линк "Appointment Manager" (строки ~311-314):
```html
<a href="/admin/agents#appointment" class="nav-link sub" data-path="/admin/agents">
  <span class="nav-agent-icon" ...>...</span>
  <span class="nav-link-text">Appointment Manager</span>
</a>
```

### Phase C — `compliance.html` (consent + audit)

**C1** — Удалить кнопку "Grant Appointment Consent" (строка ~44):
```html
<button class="cyan sm" onclick="grantAppointmentConsent()">Grant Appointment Consent</button>
```

**C2** — Удалить опции фильтра `appointment_booked` / `appointment_cancelled` (строки ~66-67):
```html
<option value="appointment_booked">Appointment Booked</option>
<option value="appointment_cancelled">Appointment Cancelled</option>
```

**C3** — Удалить функцию `grantAppointmentConsent()` (строка ~175):
```js
async function grantAppointmentConsent() { await grantConsent('appointment', 'whatsapp'); }
```

### Phase D — Документация

**D1** — Удалить файлы (содержат устаревшие планы UI):
- `docs/appointments-ui.md`
- `PLAN-REFACTOR-APPOINTMENTS-PASSTHROUGH.md`
- `PLAN-PHASE5-BOOKING.md`
- `PLAN-PHASE7-UI.md`

### Phase E — Тесты (оставить всё)

**Ничего не удаляем.** Все тесты остаются:
- `test_booking_e2e.py` — тестирует booking engine (keep)
- `test_crm_zoho.py` — appointment CRUD (keep)
- `test_crm_hubspot.py` — create_appointment (keep)
- `test_crm_webhooks.py` — sync appointment cache (keep)
- `test_crm_base.py` — abstract signatures (keep)

---

## Порядок выполнения

```
Phase A → B → C (все три сразу, UI только)
         ↓
         D (документация)
         ↓
         pytest — убедиться что 436+ тестов проходят
```

## Итог: что изменится

| До | После |
|----|-------|
| В сайдбаре "Appointment Manager" | Только "Marketing Funnel" и "Patient Follow-up" |
| В агентах таб по умолчанию "Appointment Manager" | Таб по умолчанию "Marketing Funnel" |
| В compliance кнопка дать appointment consent | Кнопка удалена |
| В compliance филтры appointment_booked/cancelled | Убраны из выпадающего списка |
| Booking engine, workflow, cache | Работают как есть |
| AI intents, CRM adapters, Calendar | Работают как есть |
