# Phase 6: Marketing & Follow-up Agents

> **Дата:** 2026-05-31
> **Базовый документ:** REBRAND-MEDICAL.md (Phase 6: Days 24–27)
> **Время:** ~4 дня

---

## 1. Цель

Создать два новых workflow-агента: **Marketing Funnel** для автоматизированных маркетинговых кампаний и **Patient Follow-up** для пост-визитного ухода. Phase 6 надстраивается поверх Phase 5 (Appointment Booking) и использует WhatsApp канал (Phase 4) для доставки сообщений.

### Marketing Funnel
- Промо-кампании (только opt-in) — сезонные напоминания (грипп, скрининги)
- Recall-кампании — ежегодные checkup'ы
- Пост-лечебные запросы отзывов
- Квалификация и нуртуринг лидов

### Patient Follow-up
- Пост-процедурные wellness checks
- Medication adherence пинг
- Сбор удовлетворённости (NPS/CSAT)
- Запрос рефералов

---

## 2. Текущее состояние (AS-IS)

### Что уже есть

| Компонент | Файл | Статус |
|-----------|------|--------|
| Workflow engine | `core/workflows/` — registry, runtime (ABC), transitions, scheduler, guards | **Есть** — полный набор |
| Appointment workflow | `core/workflows/appointment.py` | **Есть** — 16 состояний |
| Transition tables | `core/workflows/transitions.py` | **Есть** — appointment table |
| `route_event()` | `core/workflows/registry.py` | **Есть** — создаёт/загружает workflow |
| CanonicalEvent | `core/events/schemas.py` | **Есть** — 4 event type |
| WhatsApp channel | `channels/whatsapp.py` | **Есть** — webhook, _send_message |
| Intent classifier | `core/ai/intent_classifier.py` | **Есть** — medical intents |
| `simple_llm_response()` | `core/ai/generator.py` | **Есть** — async, system_override |
| ConsentManager | `core/compliance/consent.py` | **Есть** — check/grant/revoke |
| Templates | `core/communications/templates.py` | **Есть** — render_* functions (e-commerce only) |
| Workflow scheduler | `core/workflows/scheduler.py` | **Есть** — Redis sorted set |
| Admin API | `admin/workflows.py`, `admin/appointments.py` | **Есть** |
| Config YAML | `config.yaml` | **Есть** — booking секция |
| `init_workflows()` | `core/workflows/__init__.py` | **Есть** — регистрирует appointment |

### Чего нет

| Компонент | Отсутствует |
|-----------|-------------|
| `core/workflows/marketing.py` | **Нет** — state machine для маркетинговых кампаний |
| `core/workflows/followup.py` | **Нет** — state machine для пост-визитного ухода |
| Campaign triggers | **Нет** — scheduled + event-based триггеры |
| Аналитика кампаний | **Нет** — отслеживание конверсии, отправок |
| Campaign templates | **Нет** — медицинские маркетинговые шаблоны |
| Admin campaign endpoints | **Нет** |
| Event types для Phase 6 | **Нет** — campaign_scheduled, followup_due, visit_completed |
| Broadcast sending | **Нет** — WhatsApp умеет только отвечать |
| Campaign model | **Нет** — ORM модель для кампаний |

---

## 3. Архитектура (TO-BE)

### Dependency Direction

```
core/workflows/marketing.py → core/compliance/consent, core/communications, core/ai, models  (ALLOWED)
core/workflows/followup.py  → core/compliance/consent, core/communications, core/ai, models  (ALLOWED)
core/workflows/marketing.py → core/workflows/appointment  (ALLOWED — listen to appointment_booked)
core/workflows/followup.py  → core/workflows/appointment  (ALLOWED — listen to visit_completed)

channels/whatsapp.py → core/workflows  (ALLOWED — route campaign replies)

FORBIDDEN:
core/workflows/ → admin/                        (NEVER)
core/ai/ → core/workflows/                      (NEVER — LLM NEVER operates workflow state)
core/workflows/marketing.py → channels/         (NEVER — workflows don't send directly)
```

### Marketing Funnel Flow

```
Scheduled trigger (cron) / Event trigger (appointment_booked)
  ↓
route_event("campaign_scheduled")
  ↓
core/workflows/marketing.py (state machine)
  ├─ LEAD_CAPTURED → QUALIFYING
  │   ├─ LLM generates qualifying question
  │   └─ Patient response → QUALIFYING or LOST
  ├─ QUALIFYING → NURTURING
  │   ├─ Send campaign content (template)
  │   └─ Wait for response or scheduled next step
  ├─ NURTURING → APPOINTMENT_BOOKED
  │   ├─ Detect booking intent → route to AppointmentWorkflow
  │   └─ No response → LOST
  ├─ APPOINTMENT_BOOKED → FOLLOW_UP
  │   ├─ Post-appointment satisfaction check
  │   └─ Referral request
  ├─ FOLLOW_UP → CONVERTED | LOST
  └─ any → EXPIRED
```

### Patient Follow-up Flow

```
AppointmentWorkflow → COMPLETED
  ↓
route_event("visit_completed")
  ↓
core/workflows/followup.py (state machine)
  ├─ VISIT_COMPLETED → DAY_1_CHECK
  │   └─ Send "How are you feeling?" + schedule D+1
  ├─ DAY_1_CHECK → DAY_7_CHECK
  │   └─ Send wellness check + schedule D+7
  ├─ DAY_7_CHECK → DAY_30_CHECK
  │   └─ Send follow-up + schedule D+30
  ├─ DAY_30_CHECK → MEDICATION_ADHERENCE
  │   └─ Send medication reminder
  ├─ MEDICATION_ADHERENCE → SATISFACTION_SURVEY
  │   └─ Send NPS/CSAT survey
  ├─ SATISFACTION_SURVEY → CLOSED
  │   └─ Thank you + referral request
  └─ any → ESCALATED | EXPIRED
```

### LLM Boundary

```
LLM (temperature=0.3):
  MAY:  generate campaign message text, classify patient response sentiment,
        personalize content, detect interest level
  NEVER: change workflow state, trigger sends, authorize opt-out, escalate

Deterministic Engine:
  OWNS: state transitions, message delivery scheduling, consent checks,
        campaign targeting, analytics recording
```

### Broadcast Architecture

```
Admin creates campaign → campaign record in DB
  ↓
Scheduler picks up campaign_due event (cron-like polling)
  ↓
route_event("campaign_scheduled") → MarketingWorkflow
  ↓
Workflow iterates target audience:
  1. Check marketing consent (ConsentManager.is_valid)
  2. Generate message (LLM or template)
  3. Call _send_message via WhatsApp channel
  4. Record delivery in campaign analytics
  5. Wait for response or schedule next step
```

---

## 4. Задачи

### 4.1. Обновить `core/events/schemas.py` — Event Types

Добавить новые типы событий:

```python
EVENT_TYPES: set[str] = {
    # existing
    "workflow_timeout",
    "manual_escalation",
    "appointment_requested",
    "patient_message_received",
    # Phase 6 — Marketing & Follow-up
    "campaign_scheduled",       # cron-based campaign trigger
    "campaign_event",           # event-based trigger (appointment booked)
    "followup_due",             # scheduler-triggered follow-up step
    "visit_completed",          # appointment workflow signals visit done
    "patient_responded",        # patient replied to a campaign message
    "nurture_due",              # scheduled next nurture step
}
```

**Проверка:** `python -c "from app.core.events.schemas import EVENT_TYPES; assert 'campaign_scheduled' in EVENT_TYPES"` проходит.

---

### 4.2. Создать `core/workflows/marketing.py` — Marketing Funnel State Machine

#### 4.2.1. Состояния

```python
MARKETING_STATES: set[str] = {
    "LEAD_CAPTURED",        # Лид получен (из CRM, виджета, реферала)
    "QUALIFYING",           # LLM квалифицирует лида
    "NURTURING",            # Серия образовательных/промо сообщений
    "APPOINTMENT_BOOKED",   # Лид записался на приём
    "FOLLOW_UP",            # Пост-запись: отзыв, реферал
    "CONVERTED",            # Конвертирован в постоянного пациента
    "LOST",                 # Лид потерян (no response, opt-out)
    "ESCALATED",            # Передано человеку
    "EXPIRED",              # Workflow истёк
}
```

#### 4.2.2. Transition Table

```python
TRANSITION_TABLE: dict[str, list[str]] = {
    "LEAD_CAPTURED":        ["QUALIFYING", "ESCALATED", "EXPIRED"],
    "QUALIFYING":           ["NURTURING", "LEAD_CAPTURED", "LOST", "ESCALATED", "EXPIRED"],
    "NURTURING":            ["APPOINTMENT_BOOKED", "LEAD_CAPTURED", "LOST", "ESCALATED", "EXPIRED"],
    "APPOINTMENT_BOOKED":   ["FOLLOW_UP", "LOST", "ESCALATED", "EXPIRED"],
    "FOLLOW_UP":            ["CONVERTED", "LOST", "ESCALATED", "EXPIRED"],
    "CONVERTED":            ["EXPIRED"],
    "LOST":                 ["LEAD_CAPTURED", "EXPIRED"],
    "ESCALATED":            ["LEAD_CAPTURED", "CONVERTED", "LOST", "EXPIRED"],
    "EXPIRED":              [],
}
```

#### 4.2.3. `class MarketingWorkflow(Workflow)`

```python
class MarketingWorkflow(Workflow):
    async def handle_event(self, event, db):
        if event.event_type == "campaign_scheduled":
            await self._on_campaign_scheduled(event, db)
        elif event.event_type == "patient_responded":
            await self._on_patient_response(event, db)
        elif event.event_type == "nurture_due":
            await self._on_nurture_step(event, db)
        elif event.event_type == "appointment_requested":
            await self._on_appointment_booked(event, db)
```

**Методы:**

| Метод | Стейт | Действие |
|--------|-------|----------|
| `_on_campaign_scheduled()` | LEAD_CAPTURED | Проверить consent, сгенерировать первое сообщение → QUALIFYING |
| `_on_patient_response()` | QUALIFYING | LLM классифицирует ответ: интерес → NURTURING, не интерес → LOST |
| `_on_patient_response()` | NURTURING | Если `classify_intent == "appointment"` → route_event в AppointmentWorkflow. Иначе → continue nurturing |
| `_on_nurture_step()` | NURTURING | Отправить следующее сообщение в серии; если серия исчерпана → LOST |
| `_on_appointment_booked()` | NURTURING | → APPOINTMENT_BOOKED |
| `_on_patient_response()` | APPOINTMENT_BOOKED | Если прошёл приём и ответ положительный → FOLLOW_UP |
| `_on_patient_response()` | FOLLOW_UP | Если реферал/отзыв получен → CONVERTED |
| `_on_campaign_scheduled()` | LOST | Ре-триггер (если настроено) → LEAD_CAPTURED |

**Важно:** Каждое outbound сообщение проверяет `ConsentManager.is_valid(db, patient_id, "marketing", tenant_id)`. Если consent revoked → `LOST`.

**Генерация сообщений:**
- Использовать `simple_llm_response()` с `system_override` для контекста кампании
- Fallback: статический шаблон из `config.yaml` или `communications/templates.py`

**Проверка:**
- `python -c "from app.core.workflows.marketing import MarketingWorkflow"` проходит
- `validate_transition("marketing", "LEAD_CAPTURED", "QUALIFYING")` → `True`
- `validate_transition("marketing", "LEAD_CAPTURED", "CONVERTED")` → `False`

---

### 4.3. Создать `core/workflows/followup.py` — Patient Follow-up State Machine

#### 4.3.1. Состояния

```python
FOLLOWUP_STATES: set[str] = {
    "VISIT_COMPLETED",          # Визит завершён — workflow создан
    "DAY_1_CHECK",              # D+1: самочувствие
    "DAY_7_CHECK",              # D+7: восстановление
    "DAY_30_CHECK",             # D+30: долгосрочный результат
    "MEDICATION_ADHERENCE",     # Приверженность лечению
    "SATISFACTION_SURVEY",      # NPS/CSAT опрос
    "CLOSED",                   # Workflow завершён
    "ESCALATED",                # Передано человеку
    "EXPIRED",                  # Истёк
}
```

#### 4.3.2. Transition Table

```python
TRANSITION_TABLE: dict[str, list[str]] = {
    "VISIT_COMPLETED":          ["DAY_1_CHECK", "ESCALATED", "EXPIRED"],
    "DAY_1_CHECK":              ["DAY_7_CHECK", "ESCALATED", "EXPIRED"],
    "DAY_7_CHECK":              ["DAY_30_CHECK", "ESCALATED", "EXPIRED"],
    "DAY_30_CHECK":             ["MEDICATION_ADHERENCE", "ESCALATED", "EXPIRED"],
    "MEDICATION_ADHERENCE":     ["SATISFACTION_SURVEY", "ESCALATED", "EXPIRED"],
    "SATISFACTION_SURVEY":      ["CLOSED", "ESCALATED", "EXPIRED"],
    "CLOSED":                   ["EXPIRED"],
    "ESCALATED":                ["CLOSED", "EXPIRED"],
    "EXPIRED":                  [],
}
```

#### 4.3.3. `class FollowupWorkflow(Workflow)`

```python
class FollowupWorkflow(Workflow):
    async def handle_event(self, event, db):
        if event.event_type == "visit_completed":
            await self._on_visit_completed(event, db)
        elif event.event_type == "followup_due":
            await self._on_followup_step(event, db)
        elif event.event_type == "patient_responded":
            await self._on_patient_response(event, db)
```

**Методы:**

| Метод | Стейт | Действие |
|--------|-------|----------|
| `_on_visit_completed()` | VISIT_COMPLETED | Отправить "Как вы себя чувствуете?", запланировать `followup_due` через 24ч → DAY_1_CHECK |
| `_on_followup_step()` | DAY_1_CHECK | Отправить D+1 сообщение, запланировать D+7 → DAY_7_CHECK |
| `_on_followup_step()` | DAY_7_CHECK | Отправить D+7 сообщение, запланировать D+30 → DAY_30_CHECK |
| `_on_followup_step()` | DAY_30_CHECK | Отправить D+30 сообщение → MEDICATION_ADHERENCE |
| `_on_followup_step()` | MEDICATION_ADHERENCE | Спросить о приверженности лечению → SATISFACTION_SURVEY |
| `_on_followup_step()` | SATISFACTION_SURVEY | Отправить NPS опрос, запросить реферал → CLOSED |
| `_on_patient_response()` | Любой | Если ответ показывает проблему → ESCALATED. Иначе → продолжить |

**Планирование follow-up шагов:**

```python
# В _on_visit_completed:
from ..workflows.scheduler import schedule_job
schedule_job(
    key=f"followup:{self.workflow_id}:day1",
    run_at=datetime.utcnow() + timedelta(hours=24),
    payload={"workflow_id": self.workflow_id, "step": "day1"},
)
```

**Проверка:**
- `validate_transition("followup", "VISIT_COMPLETED", "DAY_1_CHECK")` → `True`
- `validate_transition("followup", "VISIT_COMPLETED", "CLOSED")` → `False`

---

### 4.4. Зарегистрировать workflow в `transitions.py` + `__init__.py`

#### `core/workflows/transitions.py`

```python
from .appointment import TRANSITION_TABLE as APPOINTMENT_TABLE
from .marketing import TRANSITION_TABLE as MARKETING_TABLE
from .followup import TRANSITION_TABLE as FOLLOWUP_TABLE

TRANSITION_TABLES: dict[str, dict[str, list[str]]] = {
    "appointment": APPOINTMENT_TABLE,
    "marketing": MARKETING_TABLE,
    "followup": FOLLOWUP_TABLE,
}
```

#### `core/workflows/__init__.py`

```python
from .appointment import AppointmentWorkflow
from .marketing import MarketingWorkflow
from .followup import FollowupWorkflow

def init_workflows() -> None:
    register_workflow("appointment", AppointmentWorkflow)
    register_workflow("marketing", MarketingWorkflow)
    register_workflow("followup", FollowupWorkflow)
```

**Проверка:**
- `init_workflows()` проходит без ошибок
- `validate_transition("marketing", "LEAD_CAPTURED", "QUALIFYING")` → `True`
- `validate_transition("followup", "VISIT_COMPLETED", "DAY_1_CHECK")` → `True`

---

### 4.5. Обновить `core/ai/intent_classifier.py` — Campaign Intents

Добавить классификацию ответов на кампании:

```python
CATEGORIES = [
    # existing
    "appointment", "reschedule", "cancel", "availability",
    "emergency", "billing", "prescription", "kb_query", "general",
    # Phase 6
    "campaign_positive",    # "Yes, I'm interested", "Sounds good"
    "campaign_negative",    # "Not interested", "Stop"
    "campaign_question",    # "Tell me more", "How much does it cost?"
    "followup_feeling_good",   # "I feel great", "No issues"
    "followup_feeling_bad",    # "I'm in pain", "Something is wrong"
    "followup_medication_ok",  # "Taking meds as prescribed"
    "followup_medication_not", # "I stopped taking them"
]

CATEGORY_DESCRIPTIONS = {
    "campaign_positive": "Positive response to a marketing campaign offer",
    "campaign_negative": "Not interested, opt-out, stop sending",
    "campaign_question": "Asking for more information about the offer",
    "followup_feeling_good": "Patient reports feeling well after procedure",
    "followup_feeling_bad": "Patient reports complications or concerns",
    "followup_medication_ok": "Patient is adherent to medication",
    "followup_medication_not": "Patient is not taking medication as prescribed",
}
```

**Проверка:** `classify_intent("Yes, I'd like to book")` возвращает `"campaign_positive"` или `"appointment"`.

---

### 4.6. Обновить `core/communications/templates.py` — Campaign + Follow-up Templates

Добавить шаблоны для Phase 6:

```python
def render_campaign_first_contact(context: dict[str, Any]) -> dict[str, str]:
    """First message in a campaign sequence."""

def render_campaign_nurture(context: dict[str, Any]) -> dict[str, str]:
    """Follow-up nurture message."""

def render_followup_day1(context: dict[str, Any]) -> dict[str, str]:
    """D+1 wellness check."""

def render_followup_day7(context: dict[str, Any]) -> dict[str, str]:
    """D+7 recovery check."""

def render_followup_day30(context: dict[str, Any]) -> dict[str, str]:
    """D+30 long-term outcome."""

def render_medication_adherence(context: dict[str, Any]) -> dict[str, str]:
    """Medication adherence check."""

def render_satisfaction_survey(context: dict[str, Any]) -> dict[str, str]:
    """NPS/CSAT survey + referral request."""
```

Каждый шаблон:
- Принимает `context` с полями: `patient_name`, `provider_name`, `clinic_name`, `appointment_date`, `custom_message`
- Возвращает `{"subject": str, "body": str}` (body = WhatsApp message text)
- Не содержит PHI (персональные данные минимизированы)
- Содержит opt-out инструкцию: "Reply STOP to opt out"

**Проверка:**
- `render_followup_day1({"patient_name": "John"})` → `{"subject": "...", "body": "Hi John, how are you feeling after your visit?..."}`
- `render_campaign_first_contact({"clinic_name": "City Clinic"})` → body содержит название клиники

---

### 4.7. Обновить `config.yaml` — Marketing & Follow-up Settings

```yaml
marketing:
  enabled: true
  max_campaigns_per_patient_per_month: 4
  cooldown_days_between_campaigns: 7
  nurture_sequence_length: 3
  nurture_days_between_steps: 3

followup:
  enabled: true
  day_1_delay_hours: 24
  day_7_delay_days: 7
  day_30_delay_days: 30
  medication_adherence_delay_days: 14
  satisfaction_survey_delay_days: 7
  escalate_on_negative_response: true

reminders:
  send_24h: true
  send_2h: true
  no_show_window_minutes: 30
```

**Проверка:** `python -c "from app.config import get_yaml_config; cfg = get_yaml_config(); assert 'marketing' in cfg"` проходит.

---

### 4.8. Обновить `channels/whatsapp.py` — Campaign Reply Routing

В `handle_webhook()`, после `classify_intent()`:

```python
intent = await classify_intent(text, str(tenant.id), history=history)

# Phase 6: route campaign/follow-up replies back to workflow
if intent in ("campaign_positive", "campaign_negative", "campaign_question",
              "followup_feeling_good", "followup_feeling_bad",
              "followup_medication_ok", "followup_medication_not"):
    event = CanonicalEvent(
        tenant_id=str(tenant.id),
        event_type="patient_responded",
        event_source="marketing",  # будет подобран active workflow
        entity_type="patient",
        entity_id=wa_id,
        payload={
            "patient_id": wa_id,
            "message": text,
            "intent": intent,
            "channel": "whatsapp",
        },
    )
    await route_event(event, db)
    return  # stop processing — workflow handles response

# existing: appointment intents
if intent in ("appointment", "reschedule", "cancel", "availability", "emergency"):
    ...
```

**Важно:** `route_event()` с `event_source="marketing"` ищет active `MarketingWorkflow` для данного пациента. Если не найден — проверяет `followup`. Если ни один не активен — падает в обычный `simple_llm_response`.

---

### 4.9. Создать `admin/marketing.py` — Campaign Admin API

```python
router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/api/campaigns")
def list_campaigns(tenant, db, status: str | None = None, offset=0, limit=50):
    """List marketing campaigns."""

@router.post("/api/campaigns")
def create_campaign(body: _CreateCampaignBody, tenant, db):
    """Create a new campaign (name, trigger, target, template)."""

@router.post("/api/campaigns/{campaign_id}/launch")
def launch_campaign(campaign_id: UUID, tenant, db):
    """Launch campaign — creates MarketingWorkflow for each target patient."""

@router.post("/api/campaigns/{campaign_id}/pause")
def pause_campaign(campaign_id: UUID, tenant, db):
    """Pause active campaign."""

@router.get("/api/campaigns/{campaign_id}/analytics")
def campaign_analytics(campaign_id: UUID, tenant, db):
    """Sent count, response rate, conversion rate."""

@router.get("/api/followups")
def list_followups(tenant, db, status: str | None = None, offset=0, limit=50):
    """List active/completed follow-up workflows."""

@router.get("/api/followups/{workflow_id}")
def get_followup(workflow_id: UUID, tenant, db):
    """Single follow-up workflow details (states, timeline)."""
```

**Pydantic модели:**

```python
class _CreateCampaignBody(BaseModel):
    name: str
    trigger_type: str           # scheduled | event
    trigger_config: dict = {}   # cron expression or event type
    target_filters: dict = {}   # specialty, age range, last visit
    message_template: str       # template name or custom prompt
    start_at: datetime | None = None
    end_at: datetime | None = None

class _CampaignAnalytics(BaseModel):
    total_contacts: int
    sent_count: int
    response_rate: float
    positive_rate: float
    appointment_booked: int
    converted: int
```

**Подключение в `admin/__init__.py`:**

```python
from . import agents, analytics, appointments, compliance, inbox, integrations, logs, marketing, pages, policies, settings, workflows
```

---

### 4.10. Wire Visit Completed → Follow-up Workflow

В `core/workflows/appointment.py`, при переходе в `COMPLETED`, отправлять событие `visit_completed`:

```python
# В _on_patient_arrived или после COMPLETED перехода:
async def _on_visit_completed(self, event, db):
    # ... existing logic ...
    if self.current_state == "COMPLETED":
        from ..registry import route_event
        visit_event = CanonicalEvent(
            tenant_id=str(self.tenant_id),
            event_type="visit_completed",
            event_source="followup",
            entity_type="patient",
            entity_id=self.customer_id,
            payload={
                "patient_id": self.customer_id,
                "workflow_id": str(self.workflow_id),
                "tenant_id": str(self.tenant_id),
            },
        )
        await route_event(visit_event, db)
```

Альтернативно: подписаться на событие через event dispatcher (когда будет реализован).

---

### 4.11. Обновить `core/ai/generator.py` — Campaign Message Generation

Добавить функцию для генерации сообщений кампании:

```python
async def generate_campaign_message(
    tenant_id,
    campaign_context: dict,
    patient_name: str,
    conversation_history: list[dict] | None = None,
) -> str:
    """Generate personalized campaign message using LLM.

    Temperature: 0.3. Fallback: static template from config.
    """
```

**Проверка:** `await generate_campaign_message(tid, {"service": "flu shot"}, "John")` возвращает строку с персонализированным сообщением.

---

## 5. Порядок выполнения

| Шаг | Задача | Файлы | Проверка |
|-----|--------|-------|----------|
| 1 | Обновить `EVENT_TYPES` — добавить campaign/follow-up типы | `core/events/schemas.py` | Импорт проходит |
| 2 | Создать `core/workflows/marketing.py` — state machine | `core/workflows/marketing.py` | `MarketingWorkflow` импортируется |
| 3 | Создать `core/workflows/followup.py` — state machine | `core/workflows/followup.py` | `FollowupWorkflow` импортируется |
| 4 | Зарегистрировать workflow в `transitions.py` + `__init__.py` | `core/workflows/transitions.py`, `__init__.py` | `validate_transition()` работает для marketing + followup |
| 5 | Обновить `intent_classifier.py` — campaign + follow-up intents | `core/ai/intent_classifier.py` | `classify_intent("I feel great")` → `followup_feeling_good` |
| 6 | Обновить `communications/templates.py` — campaign + follow-up шаблоны | `core/communications/templates.py` | Все render функции работают |
| 7 | Обновить `config.yaml` — marketing + followup секции | `config.yaml` | Конфиг читается |
| 8 | Обновить `generator.py` — campaign message generation | `core/ai/generator.py` | `generate_campaign_message()` возвращает строку |
| 9 | Обновить `whatsapp.py` — route campaign replies | `channels/whatsapp.py` | Campaign reply попадает в workflow |
| 10 | Wire visit_completed → FollowupWorkflow | `core/workflows/appointment.py` | COMPLETED триггерит follow-up |
| 11 | Создать `admin/marketing.py` — campaign API | `admin/marketing.py` | `GET /api/campaigns` → 200 |
| 12 | Подключить маркетинг в admin/__init__.py | `admin/__init__.py` | Импорт проходит |
| 13 | Финальная проверка | — | `from app.main import app` — 0 ошибок |

---

## 6. Definition of Done

1. `core/workflows/marketing.py` — `MarketingWorkflow(Workflow)` с 9 состояниями, ~20 transitions
2. `core/workflows/followup.py` — `FollowupWorkflow(Workflow)` с 9 состояниями, ~15 transitions
3. Transition tables зарегистрированы в `TRANSITION_TABLES` для `"marketing"` и `"followup"`
4. `init_workflows()` регистрирует оба workflow в `WORKFLOW_REGISTRY`
5. Event types расширены: `campaign_scheduled`, `followup_due`, `visit_completed`, `patient_responded`, `nurture_due`
6. `core/ai/intent_classifier.py` покрывает campaign/follow-up интенты
7. `core/communications/templates.py` включает campaign и follow-up шаблоны
8. `config.yaml` — секции `marketing` и `followup` с настройками
9. WhatsApp routing: campaign/follow-up replies → `route_event()`
10. Appointment COMPLETED → триггерит `FollowupWorkflow`
11. `admin/marketing.py` — API endpoints для кампаний + аналитики
12. `from app.main import app` — 0 ошибок импорта
13. Consent check перед каждым outbound маркетинговым сообщением
14. Emergency escalation: если пациент сообщает о проблеме в follow-up → `ESCALATED`

---

## 7. Структура файлов после Phase 6

```
api/app/
├── core/
│   ├── workflows/
│   │   ├── __init__.py             # 🔄 +MarketingWorkflow, FollowupWorkflow
│   │   ├── appointment.py          # 🔄 +visit_completed event on COMPLETED
│   │   ├── marketing.py            # NEW — Marketing Funnel state machine
│   │   ├── followup.py             # NEW — Patient Follow-up state machine
│   │   └── transitions.py          # 🔄 +marketing + followup tables
│   ├── ai/
│   │   ├── __init__.py             # ✅ без изменений
│   │   ├── generator.py            # 🔄 +generate_campaign_message()
│   │   └── intent_classifier.py    # 🔄 +campaign/follow-up intents
│   ├── communications/
│   │   └── templates.py            # 🔄 +campaign + follow-up templates
│   └── events/
│       └── schemas.py              # 🔄 +5 new event types
├── admin/
│   ├── __init__.py                 # 🔄 +marketing
│   ├── marketing.py                # NEW — campaign CRUD + analytics API
│   └── ...
├── channels/
│   └── whatsapp.py                 # 🔄 +campaign/follow-up reply routing
├── config.yaml                     # 🔄 +marketing + followup sections
└── main.py                         # ✅ без изменений
```

---

## 8. Риски

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| LLM генерирует неподходящий маркетинговый текст (off-label, overselling) | Средняя | Temperature 0.3 + system prompt с медицинскими ограничениями + fallback template |
| Пациент отвечает emergency в follow-up ("I'm in pain") | Средняя | Emergency keyword detection → ESCALATED + 911 message |
| Marketing consent revocation не обрабатывается мгновенно | Низкая | Проверка `ConsentManager.is_valid()` перед каждой отправкой |
| Follow-up спам (слишком много сообщений) | Низкая | Лимиты в config.yaml: cooldown_days, max_campaigns_per_month |
| WhatsApp template approval для маркетинга | Средняя | Использовать session messaging для персонализированных кампаний; шаблоны только для broadcast |
| No Redis — scheduler не работает | Средняя | Follow-up использует fallback: inline scheduling через `locked_until` + polling |
| Аналитика без dedicated storage | Низкая | In-memory aggregation + запись в Campaign модель |

---

## 9. Интеграция с Phase 3 (CRM), Phase 4 (WhatsApp), Phase 5 (Booking)

### CRM (Phase 3)
- Campaign leads могут импортироваться из CRM (Zoho/HubSpot) через `find_patient()` / `get_patient_appointments()`
- При CONVERTED → создать/обновить контакт в CRM с тегом кампании
- При LOST → обновить статус лида в CRM

### WhatsApp (Phase 4)
- Все outbound сообщения через `_send_message()` (существующий pattern)
- Campaign broadcast через тот же WhatsApp Cloud API
- Rate limiting: `config.yaml` `max_campaigns_per_patient_per_month`
- Opt-out через существующий `STOP` keyword handler

### Appointment Booking (Phase 5)
- `AppointmentWorkflow.COMPLETED` → `FollowupWorkflow` trigger
- `MarketingWorkflow.NURTURING` → если `classify_intent == "appointment"` → `route_event()` в `AppointmentWorkflow`
- `APPOINTMENT_BOOKED` состояние в Marketing = пациент записался через AppointmentWorkflow

### Compliance (Phase 2)
- Marketing consent: проверка `ConsentManager.is_valid(type="marketing")` перед каждым outbound
- Follow-up consent: тип `"appointment"` (согласие на коммуникацию по визиту)
- Audit log: каждое маркетинговое сообщение логируется
- Opt-out: мгновенная обработка STOP → `consent_manager.revoke(type="marketing")`

---

## 10. Связанные файлы

| Файл | Действие |
|------|----------|
| `core/events/schemas.py` | Обновить EVENT_TYPES |
| `core/workflows/marketing.py` | Создать |
| `core/workflows/followup.py` | Создать |
| `core/workflows/__init__.py` | Обновить `init_workflows()` |
| `core/workflows/transitions.py` | Добавить marketing + followup transition tables |
| `core/workflows/appointment.py` | Добавить `visit_completed` event на COMPLETED |
| `core/ai/intent_classifier.py` | Добавить campaign + follow-up intents |
| `core/ai/generator.py` | Добавить `generate_campaign_message()` |
| `core/communications/templates.py` | Добавить campaign + follow-up render functions |
| `admin/marketing.py` | Создать |
| `admin/__init__.py` | Добавить импорт marketing |
| `channels/whatsapp.py` | Добавить routing campaign/follow-up replies |
| `config.yaml` | Добавить marketing + followup секции |
