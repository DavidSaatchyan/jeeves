# Agent Architecture — Design & Work Plan

## 1. Motivation

Заменить сложную систему state machine воркфлоу (appointment, marketing, followup — суммарно 34 состояния) на простую архитектуру агентов. Каждый агент — это изолированный модуль, который получает событие, принимает решение через LLM + инструменты и выполняет действие. Никаких цепочек состояний, никаких транзишнов, никакого громоздкого registry/runtime.

**Почему это лучше:**
- Линейный код проще тестировать (без состояний)
- Агента можно вызывать напрямую, без роутинга через событие → registry → загрузка воркфлоу
- Каждый агент можно разрабатывать и деплоить независимо
- Не нужно синхронизировать 3 воркфлоу между собой

---

## 2. Agent Interface

```python
# agents/base.py

class Agent(ABC):
    agent_id: str          # unique name, e.g. "incoming_line"
    description: str       # human-readable purpose

    @abstractmethod
    async def handle(
        self,
        *,
        tenant_id: str,
        customer_id: str,
        db: Session,
        **kwargs,
    ) -> AgentResult:
        ...
```

```python
# agents/base.py (continued)

@dataclass
class AgentResult:
    response: str | None         # reply to send back to patient
    actions: list[AgentAction]   # side effects performed
    escalate: bool               # needs human operator
```

```python
@dataclass
class AgentAction:
    action_type: str             # e.g. "book_appointment", "send_message"
    payload: dict
    status: str                  # "success" | "failed"
```

---

## 3. Agent Registry & Dispatcher

```python
# agents/registry.py

_agents: dict[str, Agent] = {}

def register(agent: Agent) -> None:
    _agents[agent.agent_id] = agent

async def dispatch(agent_id: str, **kwargs) -> AgentResult:
    agent = _agents.get(agent_id)
    if not agent:
        raise AgentNotFoundError(agent_id)
    return await agent.handle(**kwargs)

def list_agents() -> list[Agent]:
    return list(_agents.values())
```

Вызов агента из channels/whatsapp.py:

```python
# channels/whatsapp.py (упрощённый фрагмент)

from agents.registry import dispatch

async def _handle_message(wa_id: str, text: str, tenant_id: str, ...):
    # 1. Сохранить в Conversation + Message
    # 2. Показать typing indicator
    # 3. Вызвать агента
    result = await dispatch("incoming_line",
        tenant_id=tenant_id,
        customer_id=customer_id,
        message=text,
        channel="whatsapp",
        db=db,
    )
    # 4. Отправить ответ
    if result.response:
        send_whatsapp_message(..., result.response)
    # 5. Записать AgentCall в БД
```

---

## 4. Agent «Входящая линия» (Incoming Line)

**Agent ID:** `incoming_line`
**Всегда включён:** да. Активируется каждым входящим сообщением в WhatsApp или widget.

### Flow

```
incoming_line.handle(message, tenant_id, customer_id, channel, db, ...)
│
├─ 1. Классификация (LLM call #1)
│   temperature=0.1
│   categories: "appointment_request" | "kb_query" | "general_chat" | "emergency"
│
├─ 2. Маршрутизация
│   │
│   ├─ emergency
│   │   → ответ "Срочно? Звоните в клинику", escalate=True
│   │
│   ├─ kb_query
│   │   → RAG search(tenant_id, message)
│   │   → LLM call #2: ответ на основе найденных чанков
│   │     temperature=0.3, system=из config.yaml
│   │
│   ├─ appointment_request
│   │   → Извлечь сущности: service, date_preference, provider (LLM call #2a)
│   │   → CRM get_available_slots(...)
│   │   → Если слоты есть:
│   │     → LLM call #2b: сформировать предложение слотов
│   │   → Если слотов нет:
│   │     → "Извините, на ближайшее время нет свободных слотов"
│   │   → После выбора слота пациентом:
│   │     → CRM create_appointment(...)
│   │     → AppointmentCache.create(...)
│   │     → "Запись подтверждена"
│   │
│   ├─ general_chat
│       → LLM call #2: свободный диалог
│         temperature=0.3, history=последние 15 сообщений
│
├─ 3. Сохранить AgentCall в audit_log
│
└─ 4. Вернуть AgentResult
```

### Tools (вызываемые функции)

| Tool | Source | Description |
|------|--------|-------------|
| `rag_search(query)` | `rag.engine.search` | Поиск по базе знаний |
| `get_available_slots(service, date, provider)` | `integrations/resolver` | Свободные слоты из CRM |
| `book_appointment(slot_token, patient, reason)` | `core/booking` | Подтверждение записи |
| `send_message(text)` | `channels/whatsapp` | Отправка ответа |
| `escalate_to_operator(context)` | — | Передача оператору |

### LLM Calls per Request

| Request Type | LLM Calls |
|-------------|-----------|
| `kb_query` | 2 (classify + answer) |
| `appointment_request` | 3 (classify + extract + offer) |
| `general_chat` | 2 (classify + respond) |
| `emergency` | 1 (classify only) |

### System Prompt (из config.yaml)

```yaml
agents:
  incoming_line:
    enabled: true
    model: gpt-4o-mini
    classify_temperature: 0.1
    generate_temperature: 0.3
    system_prompt: |
      You are the front desk of a medical clinic. You help patients via WhatsApp.
      - Answer medical questions using ONLY the provided knowledge base excerpts.
      - For appointment requests, extract the service, preferred date/time, and provider.
      - Never diagnose or prescribe.
      - Be warm and professional. Use the clinic's name from context.
      - If the patient mentions an emergency, respond immediately and escalate.
    kb_system_prompt: |
      Answer the patient's question using the knowledge base excerpts below.
      If the answer is not in the excerpts, say you don't have that information.
```

---

## 5. Work Plan

### New files:
- `agents/__init__.py` — exports
- `agents/base.py` — `Agent(ABC)`, `AgentResult`, `AgentAction`
- `agents/registry.py` — `register()`, `dispatch()`, `list_agents()`
- `agents/incoming_line.py` — `IncomingLineAgent` implementation
- `agents/errors.py` — `AgentNotFoundError`

### Modified files:
- `channels/whatsapp.py` — заменить route_event() на dispatch("incoming_line", ...); убрать всё, что связано с workflow routing
- `channels/widget.py` — заменить simple_llm_response() на dispatch("incoming_line", ...)
- `config.yaml` — добавить секцию `agents.incoming_line`
- `main.py` — register(incoming_line) в startup, убрать импорты воркфлоу
- `models.py` — добавить `AgentCall` модель

### Removed files:
- `core/workflows/` — весь пакет
- `core/events/` — весь пакет
- `core/communications/service.py`
- `admin/workflows.py`
- `admin/agents.py`
- `admin/marketing.py`
- `admin/policies.py`
- `admin/inbox.py`
- `admin/analytics.py`
- `templates/agents.html`, `templates/inbox.html`

### Kept (no changes):
- `core/ai/` — LLM helpers
- `core/booking/` — appointment scheduling
- `core/compliance/` — audit, consent, PHI
- `core/communications/` — delivery, webhook_sender, templates, dedup
- `integrations/` — CRM connectors
- `rag/` — RAG engine
- `knowledge/` — file management
- `shared/` — inbox_writer, idempotency, locks
- `auth/`
- `admin/cliniko.py`, `admin/pabau.py` — CRM admin pages

---

## 6. Testing Strategy

- Каждый агент тестируется изолированно (mock CRM, mock LLM)
- `test_agents_incoming_line.py` — классификация, RAG, booking
- Интеграционные тесты: webhook → agent → CRM → response
- Все LLM вызовы замоканы через unittest.mock

---

## 7. Migration Checklist

- [x] Создать `agents/` пакет с base, registry, errors
- [x] Реализовать `IncomingLineAgent.handle()`
- [x] Переписать `channels/whatsapp.py` — убрать workflow routing
- [x] Переписать `channels/widget.py` — вызывать агента
- [x] Добавить `AgentCall` модель в models.py
- [x] Обновить `main.py` — register(incoming_line) в startup
- [x] Удалить `core/workflows/` и `core/events/`
- [x] Удалить admin страницы для workflows/marketing/followup/analytics
- [x] Удалить соответствующие шаблоны
- [x] `python -c "from app.main import app"` — проверка импортов
- [x] `pytest api/tests/ -v --tb=short` — все тесты зелёные
