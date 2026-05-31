# Phase 5: Workflows — Appointment Booking

> **Дата:** 2026-05-31
> **Базовый документ:** REBRAND-MEDICAL.md (Phase 5: Days 19–23)
> **Время:** ~5 дней

---

## 1. Цель

Создать engine для бронирования appointment'ов: slot management, state machine для workflow appointment'а, медицинский intent triage, и admin API для управления записями.

Phase 5 соединяет WhatsApp канал (Phase 4) с CRM (Phase 3) через booking workflow. Пациент пишет в WhatsApp → AI классифицирует намерение → workflow appointment'а управляет слотами, подтверждением, напоминаниями.

---

## 2. Текущее состояние (AS-IS)

### Что уже есть

| Компонент | Файл | Статус |
|-----------|------|--------|
| Workflow skeleton | `core/workflows/` — registry, runtime (ABC), transitions, scheduler, guards | **Есть** — но `TRANSITION_TABLES` пуст, `init_workflows()` — placeholder |
| Patient model | `models.py:421` | **Есть** — все поля, consent |
| Appointment model | `models.py:446` | **Есть** — все поля, slot_token |
| Provider model | `models.py:493` | **Есть** — schedule (JSONB) |
| ConsentLog | `models.py:471` | **Есть** |
| CrmConnection | `models.py:509` | **Есть** |
| Intent classifier | `core/ai/intent_classifier.py` | **Есть** — базовый (appointment / kb_query / general) |
| `simple_llm_response()` | `core/ai/generator.py:76` | **Есть** — async, system_override |
| ConsentManager | `core/compliance/consent.py` | **Есть** |
| CRM adapters | `integrations/crm/` | **Есть** — Zoho (полный), HubSpot (non-PHI) |
| WhatsApp channel | `channels/whatsapp.py` | **Есть** — APIRouter, CRM bridge |
| Admin API | `admin/workflows.py` | **Есть** — GET /api/workflows |
| CanonicalEvent | `core/events/schemas.py` | **Есть** — включает `appointment_requested`, `patient_message_received` |
| Locks / Idempotency | `shared/locks.py`, `shared/idempotency.py` | **Есть** — Redis/in-memory dual mode |

### Чего нет

| Компонент | Отсутствует |
|-----------|-------------|
| `core/booking/` | **Нет** — весь пакет надо создать |
| `core/workflows/appointment.py` | **Нет** — state machine |
| `core/ai/triage.py` | **Нет** — медицинский triage |
| `admin/appointments.py` | **Нет** — API endpoints |
| Medical intents | `intent_classifier.py` не покрывает emergency, reschedule, cancel |
| Booking config | `config.yaml` не содержит настройки слотов/напоминаний |
| `init_workflows()` | Placeholder — не регистрирует workflow |

---

## 3. Архитектура (TO-BE)

### Dependency Direction

```
core/booking/ → models, config, db, shared/locks         (ALLOWED)
core/workflows/appointment.py → core/booking              (ALLOWED)
core/workflows/appointment.py → core/compliance/consent   (ALLOWED — consent checks)
core/workflows/appointment.py → core/communications       (ALLOWED — reminders)
core/ai/triage.py → core/ai (generator)                   (ALLOWED)
admin/appointments.py → core/booking, models, db          (ALLOWED)
channels/whatsapp.py → core/workflows                     (ALLOWED — trigger workflow)

FORBIDDEN:
core/booking/ → admin/, channels/                         (NEVER)
core/workflows/ → admin/                                   (NEVER)
core/ai/ → core/workflows/                                 (NEVER — LLM NEVER operates workflow state)
```

### Appointment Flow (end-to-end)

```
WhatsApp: Patient → "I need to see a doctor"
  ↓
intent_classifier.py → "appointment"
  ↓
triage.py → {intent: "book_appointment", urgency: "routine"}
  ↓
workflows/appointment.py (state machine)
  ├─ AWAITING_INTENT → CLASSIFYING
  ├─ CLASSIFYING → CHECKING_SCHEDULE
  ├─ CHECKING_SCHEDULE → OFFERING_SLOTS  ← slot_manager.get_available_slots()
  ├─ OFFERING_SLOTS → CONFIRMING         ← patient picks a slot
  ├─ CONFIRMING → BOOKED                 ← scheduler.book()
  ├─ BOOKED → REMINDER_SENT              ← scheduler (T-24h, T-2h)
  ├─ REMINDER_SENT → ARRIVED | NO_SHOW | COMPLETED
  └─ any → CANCELLED | RESCHEDULING
```

### Slot Management

```
Provider.schedule (JSONB):
{
  "monday": [{"start": "09:00", "end": "12:00"}, {"start": "13:00", "end": "17:00"}],
  "tuesday": [{"start": "09:00", "end": "17:00"}],
  ...
  "slot_duration_minutes": 30,
  "buffer_minutes": 5
}

slot_manager:
  generate_slots(provider, date) → List[Slot]
    - читает schedule для дня недели
    - нарезает на слоты по slot_duration_minutes
    - вычитает уже занятые appointment'ы
    - вычитает buffer_minutes между слотами
```

---

## 4. Задачи

### 4.1. Создать `core/booking/` — Appointment Engine

#### 4.1.1. `core/booking/__init__.py`

```python
from .slot_manager import get_available_slots, generate_slots, Slot
from .scheduler import book_appointment, reschedule_appointment, cancel_appointment, get_conflicts
```

Экспорт ключевых функций для внешнего использования.

**Проверка:** `python -c "from core.booking import get_available_slots, book_appointment"` проходит.

---

#### 4.1.2. `core/booking/slot_manager.py`

Генерация и query доступных слотов.

```python
@dataclass
class Slot:
    start: datetime
    end: datetime
    provider_name: str
    provider_specialty: str | None
    slot_token: str  # для optimistic locking

def generate_slots(
    provider: Provider,
    date: date,
    booked_slots: list[tuple[datetime, datetime]],
) -> list[Slot]:
    """Generate available time slots for a provider on a given date."""

def get_available_slots(
    db: Session,
    tenant_id: UUID,
    provider_name: str | None = None,
    specialty: str | None = None,
    date: date | None = None,
    limit: int = 10,
) -> list[Slot]:
    """Get next available slots across providers matching criteria."""
```

**Логика `generate_slots()`:**
1. Определить день недели из date
2. Прочитать `provider.schedule` для этого дня
3. Нарезать каждый временной блок на слоты длиной `slot_duration_minutes` (по умолчанию 30)
4. Вычесть пересечения с `booked_slots` (уже занятые appointment'ы)
5. Добавить buffer_minutes между слотами
6. Сгенерировать `slot_token = secrets.token_hex(16)` для каждого слота (optimistic locking)
7. Отсортировать по start
8. Вернуть до limit слотов

**Fallback:** Если `provider.schedule` пуст или не содержит дня недели → вернуть статические слоты (9:00-17:00, слот 30 мин).

**Проверка:**
- `generate_slots(provider_with_schedule, monday_date, [])` возвращает 16 слотов (8ч / 30 мин)
- `generate_slots(provider_with_schedule, monday_date, [(10:00, 10:30)])` не включает 10:00-10:30
- `get_available_slots(db, tid)` возвращает список без дубликатов

---

#### 4.1.3. `core/booking/scheduler.py`

Бронирование, перенос, отмена с optimistic locking.

```python
def book_appointment(
    db: Session,
    tenant_id: UUID,
    patient_id: UUID,
    slot_token: str,
    provider_name: str,
    start_time: datetime,
    end_time: datetime,
    reason: str | None = None,
    source: str = "whatsapp",
) -> Appointment:
    """Book an appointment with optimistic locking via slot_token."""

def reschedule_appointment(
    db: Session,
    appointment_id: UUID,
    new_slot_token: str,
    new_start: datetime,
    new_end: datetime,
    new_provider_name: str | None = None,
) -> Appointment:
    """Reschedule existing appointment."""

def cancel_appointment(
    db: Session,
    appointment_id: UUID,
    reason: str | None = None,
) -> bool:
    """Cancel appointment (soft delete — set status='cancelled')."""

def get_conflicts(
    db: Session,
    tenant_id: UUID,
    provider_name: str,
    start_time: datetime,
    end_time: datetime,
    exclude_appointment_id: UUID | None = None,
) -> list[Appointment]:
    """Find overlapping appointments for a provider."""
```

**Логика `book_appointment()`:**
1. Проверить `appointments` на пересечение времен (вызвать `get_conflicts()`)
2. Если конфликт есть → проверить `slot_token` оптимистично (запрос `SELECT ... WHERE slot_token = :token AND status = 'scheduled'`)
   - Если слот занят другим — `raise SlotAlreadyBookedError`
3. Создать `Appointment` row со статусом `"scheduled"`
4. Вернуть созданный Appointment

**Optimistic locking через slot_token:**
```sql
-- При создании appointment'а:
INSERT INTO appointments (..., slot_token, status)
VALUES (..., :token, 'scheduled');

-- Но перед этим проверяем:
SELECT COUNT(*) FROM appointments
WHERE slot_token = :token AND status IN ('scheduled', 'confirmed', 'arrived', 'in_progress');
-- Если > 0 → конфликт
```

**Проверка:**
- `book_appointment(...)` создаёт Appointment в БД
- `book_appointment(...)` с конфликтующим slot_token → `SlotAlreadyBookedError`
- `cancel_appointment(id)` → `appointment.status == "cancelled"`
- `get_conflicts(provider, 10:00-10:30)` находит пересекающиеся appointment'ы

---

#### 4.1.4. `core/booking/calendar_sync.py` — Stub для Google/Outlook

```python
"""Calendar sync — Phase 5 stub. Full implementation in Phase 6+.
Interface documented for future integration."""

async def push_to_calendar(appointment: Appointment, provider: str = "google") -> str | None:
    """Push appointment to external calendar. Returns external event ID or None."""

async def pull_from_calendar(provider: str, calendar_id: str) -> list[dict]:
    """Pull events from external calendar."""

async def sync_calendar(tenant_id: UUID, provider: str) -> dict:
    """Bi-directional sync stub. Returns stats dict."""
```

Все методы — логируют вызов и возвращают `None` / `[]` / `{"synced": 0}`.

**Проверка:** `python -c "from core.booking.calendar_sync import push_to_calendar"` проходит.

---

### 4.2. Создать `core/workflows/appointment.py` — State Machine

#### 4.2.1. Состояния и Transition Table

```python
APPOINTMENT_STATES: set[str] = {
    "STARTED",          # Workflow создан
    "AWAITING_INTENT",  # Ожидаем уточнения намерения
    "CLASSIFYING",      # LLM классифицирует (book / reschedule / cancel / availability)
    "CHECKING_SCHEDULE", # Проверяем доступные слоты
    "OFFERING_SLOTS",   # Предлагаем слоты пациенту (ожидаем выбора)
    "CONFIRMING",       # Подтверждаем выбор
    "BOOKED",           # Забронировано
    "RESCHEDULING",     # Перенос записи
    "CANCELLING",       # Отмена записи
    "REMINDER_SENT",    # Напоминание отправлено
    "ARRIVED",          # Пациент пришёл
    "NO_SHOW",          # Пациент не явился
    "COMPLETED",        # Приём завершён
    "CANCELLED",        # Отменено
    "ESCALATED",        # Передано человеку
    "EXPIRED",          # Workflow истёк
}

TRANSITION_TABLES["appointment"] = {
    "STARTED":              ["AWAITING_INTENT"],
    "AWAITING_INTENT":      ["CLASSIFYING", "ESCALATED", "EXPIRED"],
    "CLASSIFYING":          ["CHECKING_SCHEDULE", "AWAITING_INTENT", "CANCELLING", "ESCALATED"],
    "CHECKING_SCHEDULE":    ["OFFERING_SLOTS", "AWAITING_INTENT", "CANCELLED", "ESCALATED"],
    "OFFERING_SLOTS":       ["CONFIRMING", "AWAITING_INTENT", "CANCELLED", "ESCALATED"],
    "CONFIRMING":           ["BOOKED", "OFFERING_SLOTS", "CANCELLED", "ESCALATED"],
    "RESCHEDULING":         ["CHECKING_SCHEDULE", "BOOKED", "CANCELLED", "ESCALATED"],
    "CANCELLING":           ["CANCELLED", "AWAITING_INTENT"],
    "BOOKED":               ["REMINDER_SENT", "RESCHEDULING", "CANCELLING", "NO_SHOW", "COMPLETED", "ESCALATED"],
    "REMINDER_SENT":        ["ARRIVED", "NO_SHOW", "RESCHEDULING", "CANCELLING"],
    "ARRIVED":              ["COMPLETED", "NO_SHOW"],
    "NO_SHOW":              ["BOOKED", "COMPLETED", "CANCELLED"],
    "COMPLETED":            ["EXPIRED"],
    "CANCELLED":            ["EXPIRED"],
    "ESCALATED":            ["AWAITING_INTENT", "CANCELLED", "COMPLETED", "EXPIRED"],
    "EXPIRED":              [],
}
```

#### 4.2.2. `class AppointmentWorkflow(Workflow)`

```python
class AppointmentWorkflow(Workflow):
    """Appointment booking state machine."""

    async def handle_event(self, event: CanonicalEvent, db: Session) -> None:
        if event.event_type == "patient_message_received":
            await self._on_patient_message(event, db)
        elif event.event_type == "appointment_requested":
            await self._on_appointment_request(event, db)
        elif event.event_type == "slot_selected":
            await self._on_slot_selected(event, db)
        elif event.event_type == "reminder_due":
            await self._on_reminder_due(event, db)
        elif event.event_type == "patient_arrived":
            await self._on_patient_arrived(event, db)
        elif event.event_type == "no_show_detected":
            await self._on_no_show(event, db)
```

**Методы состояний:**

| Метод | Стейт | Действие |
|--------|-------|----------|
| `_on_patient_message()` | AWAITING_INTENT | Вызвать `triage.classify()`, перейти в CLASSIFYING или CANCELLING |
| `_on_patient_message()` | CLASSIFYING | Если triage → `book` → CHECKING_SCHEDULE. `cancel` → CANCELLING. `reschedule` → CHECKING_SCHEDULE |
| `_on_patient_message()` | CHECKING_SCHEDULE | Вызвать `slot_manager.get_available_slots()`, перейти в OFFERING_SLOTS |
| `_on_patient_message()` | OFFERING_SLOTS | Если сообщение содержит выбор слота → CONFIRMING |
| `_on_slot_selected()` | CONFIRMING | `scheduler.book_appointment()` → BOOKED. Если ошибка → OFFERING_SLOTS |
| `_on_patient_message()` | BOOKED | Если просьба отменить → CANCELLING. Если перенести → RESCHEDULING |
| `_on_reminder_due()` | BOOKED | Отправить reminder → REMINDER_SENT |
| `_on_patient_arrived()` | REMINDER_SENT | → ARRIVED |
| `_on_no_show()` | REMINDER_SENT / BOOKED | → NO_SHOW |
| `_on_patient_message()` | CANCELLING | `scheduler.cancel_appointment()` → CANCELLED |

**Регистрация:**

В `core/workflows/__init__.py`:
```python
from .appointment import AppointmentWorkflow

def init_workflows() -> None:
    register_workflow("appointment", AppointmentWorkflow)
```

В `core/workflows/transitions.py`:
```python
from .appointment import TRANSITION_TABLES as APPT_TABLES
TRANSITION_TABLES.update(APPT_TABLES)
```

**Проверка:**
- `python -c "from core.workflows.appointment import AppointmentWorkflow"` проходит
- `python -c "from core.workflows import init_workflows; init_workflows()"` проходит
- `validate_transition("appointment", "STARTED", "AWAITING_INTENT")` → `True`
- `validate_transition("appointment", "STARTED", "BOOKED")` → `False`

---

### 4.3. Создать `core/ai/triage.py` — Medical Intent Triage

LLM boundary: классифицирует сообщение пациента, НЕ выполняет действия.

```python
MEDICAL_INTENTS = {
    "book_appointment": "Patient wants to schedule a new appointment",
    "reschedule": "Patient wants to change an existing appointment time",
    "cancel_appointment": "Patient wants to cancel an existing appointment",
    "check_availability": "Patient asking about available times/slots",
    "emergency": "Patient expressing urgent/emergency medical need",
    "general_question": "General clinic question (hours, location, insurance)",
    "billing_question": "Question about payment, insurance, costs",
    "prescription_request": "Request for prescription refill",
    "lab_result": "Question about lab/test results",
    "follow_up": "Post-visit follow-up or question",
    "greeting": "Greeting, small talk, unclear",
}

async def triage_intent(
    message: str,
    conversation_history: list[dict] | None = None,
    tenant_id: str | None = None,
) -> dict:
    """Classify patient message into medical intent.

    Returns:
        {"intent": "book_appointment", "urgency": "routine", "confidence": 0.95,
         "entities": {"doctor": "Dr. Smith", "date": "tomorrow"}}

    Temperature: 0.1. Fallback: {"intent": "general_question", "urgency": "routine"}.
    """
```

**Промпт:**
```
You are a medical triage assistant. Classify the patient's message into exactly one intent.
Also assess urgency (routine / urgent / emergency) and extract relevant entities.

Intents:
- book_appointment: ...
- reschedule: ...
...

Message: {message}
History: {history}

Respond with JSON: {"intent": "...", "urgency": "...", "confidence": 0.0-1.0, "entities": {}}
```

**Fallback:** Если LLM не доступен → `{"intent": "general_question", "urgency": "routine", "confidence": 0.0, "entities": {}}`.

**Важно:** Если `urgency == "emergency"` → workflow должен немедленно перейти в `ESCALATED` и отправить сообщение с номером экстренной службы.

**Проверка:**
- `await triage_intent("I need to see a doctor tomorrow")` → `{"intent": "book_appointment", ...}`
- `await triage_intent("Cancel my appointment")` → `{"intent": "cancel_appointment", ...}`
- `await triage_intent("I'm having chest pain")` → `{"intent": "book_appointment", "urgency": "emergency", ...}`
- `await triage_intent("")` → fallback

---

### 4.4. Обновить `core/ai/intent_classifier.py`

Добавить поддержку медицинских суб-интентов:

```python
async def classify_intent(message: str, tenant_id: str, history: list[dict] | None = None) -> str:
    # Existing: appointment, kb_query, general
    # ADD: emergency, reschedule, cancel, availability, billing, prescription
```

Новые категории:
- `emergency` — сообщение об экстренной ситуации (боль, травма)
- `reschedule` — просьба перенести запись
- `cancel` — просьба отменить запись
- `availability` — вопрос о свободных слотах
- `billing` — вопрос об оплате/страховке
- `prescription` — запрос рецепта

**Проверка:** `classify_intent("I need to reschedule")` возвращает `"reschedule"`.

---

### 4.5. Обновить `core/ai/__init__.py`

```python
from .generator import simple_llm_response, translate_query
from .triage import triage_intent
from .intent_classifier import classify_intent

__all__ = [
    "simple_llm_response",
    "translate_query",
    "triage_intent",
    "classify_intent",
]
```

---

### 4.6. Создать `admin/appointments.py` — Admin API

CRUD endpoints для управления appointment'ами.

```python
router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/api/appointments")
def list_appointments(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    status: str | None = Query(None),
    provider: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    patient_id: UUID | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """List appointments with filtering and pagination."""

@router.get("/api/appointments/{appointment_id}")
def get_appointment(
    appointment_id: UUID,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    """Get single appointment details."""

@router.post("/api/appointments")
def create_appointment(
    body: _CreateAppointmentBody,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    """Create appointment manually from admin panel."""

@router.patch("/api/appointments/{appointment_id}")
def update_appointment(
    appointment_id: UUID,
    body: _UpdateAppointmentBody,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    """Update appointment (status, notes, time)."""

@router.post("/api/appointments/{appointment_id}/cancel")
def cancel_appointment_endpoint(
    appointment_id: UUID,
    body: _CancelAppointmentBody,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    """Cancel appointment."""

@router.get("/api/providers")
def list_providers(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    specialty: str | None = Query(None),
):
    """List healthcare providers."""

@router.get("/api/appointments/slots")
def available_slots(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    provider_name: str | None = Query(None),
    specialty: str | None = Query(None),
    date: str | None = Query(None),
):
    """Get available appointment slots."""
```

**Pydantic модели (в том же файле):**

```python
class _CreateAppointmentBody(BaseModel):
    patient_id: UUID
    provider_name: str
    start_time: datetime
    end_time: datetime
    reason: str | None = None
    source: str = "admin"

class _UpdateAppointmentBody(BaseModel):
    status: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    provider_name: str | None = None
    notes: str | None = None
    reason: str | None = None

class _CancelAppointmentBody(BaseModel):
    reason: str | None = None
```

**Проверка:**
- `GET /admin/api/appointments` → 200, список
- `GET /admin/api/appointments?status=scheduled` → фильтр
- `POST /admin/api/appointments` → 200, создан
- `POST /admin/api/appointments/{id}/cancel` → 200, status="cancelled"
- `GET /admin/api/providers` → список врачей
- `GET /admin/api/appointments/slots` → слоты

---

### 4.7. Подключить `admin/appointments.py` в `admin/__init__.py`

```python
from . import agents, analytics, compliance, inbox, integrations, logs, pages, policies, settings, workflows, appointments
```

**Проверка:** `python -c "from app.admin import router"` проходит.

---

### 4.8. Обновить `config.yaml` — booking settings

```yaml
booking:
  slot_duration_minutes: 30
  buffer_minutes: 5
  max_slots_to_offer: 5
  default_start_hour: 9
  default_end_hour: 17
  reminders:
    send_24h: true
    send_2h: true
    no_show_window_minutes: 30
```

**Проверка:** `python -c "from app.config import get_yaml_config; cfg = get_yaml_config(); assert 'booking' in cfg"` проходит.

---

### 4.9. Обновить `main.py` — инициализация workflows на startup

```python
@app.on_event("startup")
def on_startup() -> None:
    from .core.workflows import init_workflows
    init_workflows()
    # ... existing code (alembic, channel cache)
```

**Проверка:** `python -c "from app.main import app"` проходит.

---

### 4.10. Создать Alembic миграцию (если нужно)

**Проверить модель `Appointment`:**
| Поле | Статус | Назначение |
|------|--------|------------|
| `id` | ✅ | UUID PK |
| `tenant_id` | ✅ | FK → tenants, indexed |
| `patient_id` | ✅ | FK → patients, indexed |
| `external_id` | ✅ | CRM appointment ID |
| `provider_name` | ✅ | |
| `provider_specialty` | ✅ | |
| `department` | ✅ | |
| `start_time` | ✅ | |
| `end_time` | ✅ | |
| `status` | ✅ | scheduled/confirmed/arrived/in_progress/completed/cancelled/no_show/rescheduled |
| `reason` | ✅ | |
| `notes` | ✅ | |
| `source` | ✅ | whatsapp/widget/crm/web/admin |
| `slot_token` | ✅ | |
| `reminder_sent_24h` | ✅ | |
| `reminder_sent_2h` | ✅ | |
| `consent_id` | ✅ | |

**Проверить модель `Provider`:**
| Поле | Статус |
|------|--------|
| `id` | ✅ |
| `tenant_id` | ✅ |
| `external_id` | ✅ |
| `name` | ✅ |
| `specialty` | ✅ |
| `email` | ✅ |
| `phone` | ✅ |
| `schedule` (JSONB) | ✅ |

**Миграция не требуется** — все поля уже существуют.

---

### 4.11. Wire WhatsApp → Appointment Workflow

Обновить `channels/whatsapp.py`: после того как `intent_classifier` возвращает `"appointment"`, запустить workflow вместо обычного `simple_llm_response`.

```python
# В handle_webhook(), после moderate() и consent:
intent = await classify_intent(text, str(tenant.id), history=history)

if intent in ("appointment", "reschedule", "cancel", "availability"):
    # Создать CanonicalEvent и запустить workflow
    from ..core.events.schemas import CanonicalEvent
    from ..core.workflows.registry import route_event

    event = CanonicalEvent(
        tenant_id=str(tenant.id),
        event_type="patient_message_received",
        event_source="appointment",
        entity_type="patient",
        entity_id=wa_id,
        payload={
            "patient_id": wa_id,
            "message": text,
            "contact_name": contact_name,
            "channel": "whatsapp",
        },
    )
    await route_event(event, db)
else:
    # Обычный AI response
    result = await simple_llm_response(...)
```

**Важно:** Workflow запускается **детерминированно** (через `route_event()`), не через LLM. LLM только классифицирует интент.

---

## 5. Порядок выполнения

| Шаг | Задача | Файлы | Проверка |
|-----|--------|-------|----------|
| 1 | Создать `core/booking/slot_manager.py` — генерация слотов | `core/booking/__init__.py`, `core/booking/slot_manager.py` | `get_available_slots()` возвращает слоты |
| 2 | Создать `core/booking/scheduler.py` — бронирование + locking | `core/booking/scheduler.py` | `book_appointment()` создаёт Appointment |
| 3 | Создать `core/booking/calendar_sync.py` — stub | `core/booking/calendar_sync.py` | Импорт проходит |
| 4 | Создать `core/workflows/appointment.py` — state machine | `core/workflows/appointment.py` | `AppointmentWorkflow` импортируется |
| 5 | Зарегистрировать workflow в `transitions.py` + `__init__.py` | `core/workflows/transitions.py`, `core/workflows/__init__.py` | `validate_transition("appointment", ...)` работает |
| 6 | Создать `core/ai/triage.py` — medical intent triage | `core/ai/triage.py` | `triage_intent("I need a doctor")` → `book_appointment` |
| 7 | Обновить `core/ai/intent_classifier.py` — medical intents | `core/ai/intent_classifier.py` | `classify_intent("reschedule")` → `"reschedule"` |
| 8 | Обновить `core/ai/__init__.py` — экспорт | `core/ai/__init__.py` | `from core.ai import triage_intent` проходит |
| 9 | Создать `admin/appointments.py` — CRUD API | `admin/appointments.py` | `GET /admin/api/appointments` → 200 |
| 10 | Подключить appointments.py в admin/__init__.py | `admin/__init__.py` | `python -c "from app.admin import router"` |
| 11 | Обновить `config.yaml` — booking settings | `config.yaml` | Конфиг читается |
| 12 | Обновить `main.py` — init_workflows на startup | `main.py` | `from app.main import app` проходит |
| 13 | Wire WhatsApp → Appointment workflow | `channels/whatsapp.py` | Intent "appointment" запускает workflow |
| 14 | Финальная проверка | — | `from app.main import app` — 0 ошибок |

---

## 6. Definition of Done

1. `core/booking/slot_manager.py` — генерация слотов из `Provider.schedule`, вычитание занятых, `get_available_slots()`
2. `core/booking/scheduler.py` — `book_appointment()`, `reschedule_appointment()`, `cancel_appointment()`, `get_conflicts()` с optimistic locking через `slot_token`
3. `core/booking/calendar_sync.py` — stub с документированным интерфейсом
4. `core/workflows/appointment.py` — `AppointmentWorkflow(Workflow)` с полным state machine (16 состояний, ~30 transitions)
5. Transition table зарегистрирована в `TRANSITION_TABLES`
6. `init_workflows()` регистрирует `AppointmentWorkflow` в `WORKFLOW_REGISTRY`
7. `core/ai/triage.py` — `triage_intent()` возвращает `{intent, urgency, confidence, entities}`
8. `core/ai/intent_classifier.py` — расширен для медицинских интентов (emergency, reschedule, cancel, availability, billing, prescription)
9. `admin/appointments.py` — 7 endpoints: list/get/create/update/cancel appointments + providers + slots
10. `config.yaml` — секция `booking` со всеми настройками
11. `main.py` вызывает `init_workflows()` на startup
12. WhatsApp → Appointment workflow: intent `"appointment"` запускает `route_event()` вместо `simple_llm_response()`
13. `from app.main import app` — 0 ошибок импорта
14. Emergency intents (`urgency == "emergency"`) → `ESCALATED` + сообщение с номером экстренной службы

---

## 7. Структура файлов после Phase 5

```
api/app/
├── core/
│   ├── booking/                    # NEW
│   │   ├── __init__.py             # Экспорт slot_manager + scheduler
│   │   ├── slot_manager.py         # Генерация слотов
│   │   ├── scheduler.py            # Бронирование + locking
│   │   └── calendar_sync.py        # Stub для Google/Outlook
│   ├── workflows/
│   │   ├── __init__.py             # 🔄 init_workflows() регистрирует AppointmentWorkflow
│   │   ├── registry.py             # ✅ без изменений
│   │   ├── runtime.py              # ✅ без изменений
│   │   ├── transitions.py          # 🔄 +appointment transition table
│   │   ├── guards.py               # ✅ без изменений
│   │   ├── scheduler.py            # ✅ без изменений
│   │   └── appointment.py          # NEW — AppointmentWorkflow
│   └── ai/
│       ├── __init__.py             # 🔄 +triage_intent
│       ├── generator.py            # ✅ без изменений
│       ├── intent_classifier.py    # 🔄 +medical intents
│       └── triage.py               # NEW — medical intent triage
├── admin/
│   ├── __init__.py                 # 🔄 +appointments
│   ├── appointments.py             # NEW — CRUD API
│   ├── ... (existing files)
├── channels/
│   └── whatsapp.py                 # 🔄 +workflow trigger on "appointment" intent
├── config.yaml                     # 🔄 +booking section
└── main.py                         # 🔄 +init_workflows() on startup
```

---

## 8. Риски

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| Slot race condition (два пациента бронируют один слот) | Средняя | Optimistic locking через `slot_token` + проверка при INSERT |
| LLM misclassifies intent (например, "I'm dying" → general_question) | Низкая | Temperature 0.1 + emergency detection отдельным правилом (keyword match before LLM) |
| Provider.schedule format inconsistent между tenant'ами | Средняя | Валидация schedule при сохранении Provider; fallback на default 9-17 |
| Workflow state explosion (невалидные переходы) | Низкая | `validate_transition()` в runtime; тесты на все переходы |
| Calendar sync complexity | Низкая (Phase 5) | Stub — полная реализация в Phase 6+ |
| Appointment без patient_id в WhatsApp | Средняя | CRM bridge создаёт пациента до workflow; если нет — запросить данные |
| Reminder scheduling без Redis | Средняя | `scheduler.py` возвращает `[]` без Redis; reminders не отправляются — fallback в workflow |

---

## 9. Интеграция с Phase 3 (CRM) и Phase 4 (WhatsApp)

### CRM (Phase 3)
- После `book_appointment()` → вызвать `adapter.create_appointment()` в CRM
- После `cancel_appointment()` → вызвать `adapter.cancel_appointment()` в CRM
- `get_available_slots()` может вызывать `adapter.search_available_slots()` если настроено

### WhatsApp (Phase 4)
- `intent_classifier` в `whatsapp.py` → если `"appointment"` → запустить workflow
- Workflow отправляет сообщения обратно через `_send_message()` WhatsApp Cloud API
- Выбор слота через WhatsApp → парсинг ответа пациента в `OFFERING_SLOTS` state

### Emergency Detection (Critical)
```python
# В triage.py, перед LLM:
EMERGENCY_KEYWORDS = {"chest pain", "can't breathe", "severe bleeding", "heart attack",
                      "stroke", "suicidal", "emergency", " ambulance", "911", "112"}

if any(kw in message.lower() for kw in EMERGENCY_KEYWORDS):
    return {"intent": "book_appointment", "urgency": "emergency", "confidence": 1.0, "entities": {}}
```

---

## 10. Связанные файлы

| Файл | Действие |
|------|----------|
| `core/booking/__init__.py` | Создать |
| `core/booking/slot_manager.py` | Создать |
| `core/booking/scheduler.py` | Создать |
| `core/booking/calendar_sync.py` | Создать (stub) |
| `core/workflows/appointment.py` | Создать |
| `core/workflows/__init__.py` | Обновить `init_workflows()` |
| `core/workflows/transitions.py` | Добавить appointment transition table |
| `core/ai/triage.py` | Создать |
| `core/ai/intent_classifier.py` | Обновить — medical intents |
| `core/ai/__init__.py` | Обновить — экспорт triage_intent |
| `admin/appointments.py` | Создать |
| `admin/__init__.py` | Обновить — импорт appointments |
| `config.yaml` | Обновить — booking секция |
| `main.py` | Обновить — init_workflows на startup |
| `channels/whatsapp.py` | Обновить — workflow trigger на appointment intent |
