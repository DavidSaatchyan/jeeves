# Phase 1: Агенты (Команда ИИ)

Основание: раздел ////3333//// из `new structure.md`.

---

## 1. Список агентов — `/admin/agents`

**Файл:** `templates/agents_list.html` (новый)

Сетка карточек (Card Grid). Каждая карточка — бизнес-роль ИИ.

### Карточка «Входящая линия»
- Статус: 🟢 Активен / ⚪ Выключен (тумблер)
- Метрика: «Обработано X чатов за месяц»
- Иконки каналов: WhatsApp, Виджет

### Карточка «Агент-Маркетолог» (заглушка)
- Статус: ⚪ Доступен к подключению (или 🔒 Доступно на тарифе Pro)
- Описание: «Автоматически возвращает спящих пациентов, предлагает акции»

### Карточка «Контроль качества» (заглушка)
- Описание: «Пишет пациенту через 2 часа после приема, собирает оценки и отзывы»

---

## 2. Страница настройки агента — `/admin/agents/{agent_id}`

**Файл:** `templates/agent_detail.html` (новый)

Двухпанельный макет:
- Слева (60-65%) — 4 вкладки с настройками
- Справа (35-40%) — Playground (симулятор чата, постоянно виден)

---

### 2.1 Таб 1: Личность и Характер

Поля:
| Поле | Ключ в `agent_config` | Тип | UI |
|------|----------------------|-----|----|
| Имя робота | `personality.name` | Text | `<input>` |
| Пол | `personality.gender` | Radio | Мужской / Женский |
| Tone of Voice | `personality.tov` | Radio | `expert` / `friendly` / `humorous` |
| Системный промпт | `personality.system_prompt` | Textarea | с предзаполненным шаблоном |

---

### 2.2 Таб 2: Навыки и Бизнес-правила

#### Capabilities (тумблеры)

| Ключ | UI | По умолчанию |
|------|----|------------|
| `skills.capabilities.search_slots` | Поиск свободных слотов | `true` |
| `skills.capabilities.hold_slot` | Резервирование (Hold на 10 мин) | `true` |
| `skills.capabilities.create_booking` | Создание финальной записи | `true` |
| `skills.capabilities.reschedule` | Перенос записи | `false` |
| `skills.capabilities.cancel` | Отмена записи | `false` |

#### Hard Rules (числовые поля)

| Ключ | UI | По умолчанию |
|------|----|------------|
| `skills.hard_rules.min_hours_before` | Минимальное время до приема | `2` |
| `skills.hard_rules.booking_depth_days` | Глубина записи | `14` |
| `skills.hard_rules.prevent_duplicates` | Защита от дублей | `true` (всегда включено) |

---

### 2.3 Таб 3: Подключение Базы Знаний

- `knowledge_folders`: `string[]` — список ID папок, доступных агенту
- API: `GET /admin/api/knowledge/tree` — возвращает дерево папок

---

### 2.4 Таб 4: Каналы связи

- `channels.whatsapp`: ID канала WhatsApp или null
- `channels.widget`: ID канала Widget или null
- API: `GET /admin/api/channels` — уже есть

---

## 3. Playground (Песочница)

Правая панель. Симулятор чата с визуализацией шагов агента.

**API:** `POST /admin/api/agents/{agent_id}/playground`

Body: `{message, config_override?}` где `config_override` — временный `agent_config` для симуляции.

Response:
```json
{
  "response": "...",
  "steps": [
    {"icon": "🔍", "label": "Поиск в Базе знаний", "detail": "Найден файл: Лазер_Эпиляция.pdf"},
    {"icon": "📡", "label": "Запрос в Cliniko API", "detail": "Доступные слоты: ..."},
    {"icon": "🚫", "label": "Бизнес-правило", "detail": "Минимальное время 2ч — заблокировано"},
    {"icon": "🤖", "label": "Ответ ИИ", "detail": "..."}
  ],
  "intent": "appointment",
  "latency_ms": 1200
}
```

Логика: запускает `IncomingLineAgent.handle()` с временным `agent_config` (не сохраняя в БД), перехватывает логи для шагов.

Кнопки:
- `[ Обновить агента ]` — перезапускает симуляцию с текущими настройками левой панели
- `[ Опубликовать ]` — `PUT /admin/api/agents/{agent_id}/publish` — сохраняет `agent_config` и применяет каналы

---

## 4. Бэкенд — модель данных

### 4.1 `models.py`

```python
class Tenant(Base):
    ...
    agent_config = Column(JSONB, default=dict)  # всё: personality, skills, knowledge_folders, channels, enabled
```

### 4.2 Default config

```python
# agents/default_config.py (новый файл)
def get_default_agent_config() -> dict:
    return {
        "enabled": True,
        "personality": {
            "name": "Ассистент",
            "gender": "female",
            "tov": "friendly",
            "system_prompt": (
                "Ты — front desk медицинской клиники. "
                "Отвечай вежливо и профессионально. "
                "Никогда не ставь диагнозы. "
                "Если пациент описывает симптомы — предложи запись на приём."
            ),
        },
        "skills": {
            "capabilities": {
                "search_slots": True,
                "hold_slot": True,
                "create_booking": True,
                "reschedule": False,
                "cancel": False,
            },
            "hard_rules": {
                "min_hours_before": 2,
                "booking_depth_days": 14,
                "prevent_duplicates": True,
            },
        },
        "knowledge_folders": [],
        "channels": {
            "whatsapp": None,
            "widget": None,
        },
    }
```

### 4.3 Data flow

```
[UI] → PUT /admin/api/agents/{id}/config
      → admin/agents.py: читает tenant, обновляет tenant.agent_config["personality"]
      → db.commit()
      → IncomingLineAgent.handle() читает tenant.agent_config при каждом вызове
```

### 4.4 Alembic migration

```python
# add_agent_config_to_tenants
op.add_column("tenants", Column("agent_config", JSON, default=dict))
```

### 4.5 Stats endpoint

`GET /admin/api/agents/{agent_id}/stats` → `{conversations_this_month: int}`

Считает `ChatLog` за текущий месяц по `tenant_id` + `channel` (каналы, привязанные к агенту).

---

## 5. API endpoints

Все в `admin/agents.py`. Старые роуты (feed, funnel, queue, policy, resolve) НЕ трогать.

| Метод | Путь | Назначение | Body / Params |
|-------|------|-----------|--------------|
| `GET` | `/admin/agents` | SSR — список агентов | — |
| `GET` | `/admin/agents/{agent_id}` | SSR — детальная настройка | — |
| `GET` | `/admin/api/agents` | JSON список агентов | — |
| `GET` | `/admin/api/agents/{agent_id}/config` | Полный `agent_config` | — |
| `PUT` | `/admin/api/agents/{agent_id}/config` | Сохранить `personality` | `{name, gender, tov, system_prompt}` |
| `PUT` | `/admin/api/agents/{agent_id}/skills` | Сохранить `skills` | `{capabilities: {...}, hard_rules: {...}}` |
| `PUT` | `/admin/api/agents/{agent_id}/knowledge` | Сохранить `knowledge_folders` | `{folder_ids: [...]}` |
| `PUT` | `/admin/api/agents/{agent_id}/channels` | Сохранить `channels` | `{whatsapp: "id"\|null, widget: "id"\|null}` |
| `POST` | `/admin/api/agents/{agent_id}/toggle` | Вкл/выкл | `{enabled: bool}` |
| `POST` | `/admin/api/agents/{agent_id}/publish` | Опубликовать на живые каналы | — |
| `POST` | `/admin/api/agents/{agent_id}/playground` | Симуляция | `{message, config_override?}` |
| `GET` | `/admin/api/agents/{agent_id}/stats` | Метрики для карточки | — |
| `GET` | `/admin/api/knowledge/tree` | Дерево папок (для таба 3) | — |

---

## 6. IncomingLineAgent — изменения

### 6.1 Читать `tenant.agent_config` вместо `config.yaml`

```python
# agents/incoming_line.py
class IncomingLineAgent(Agent):
    async def handle(self, *, tenant_id, customer_id, db, **kwargs):
        tenant = db.get(Tenant, tenant_id)
        cfg = tenant.agent_config or {}
        personality = cfg.get("personality", {})
        skills = cfg.get("skills", {})
        caps = skills.get("capabilities", {})
        rules = skills.get("hard_rules", {})
        knowledge_folders = cfg.get("knowledge_folders", [])
        enabled = cfg.get("enabled", True)

        if not enabled:
            return AgentResult(response=None, escalate=True)

        # system_prompt из настроек, не из config.yaml
        system_prompt = personality.get("system_prompt", DEFAULT_SYSTEM_PROMPT)
```

### 6.2 Capabilities — гейт на действия

```python
if intent in ("appointment", "reschedule", "availability"):
    if not caps.get("search_slots", True):
        return AgentResult(response="...", escalate=True)
    return await _handle_appointment(...)
```

### 6.3 Knowledge folders — фильтр RAG

```python
if intent == "kb_query":
    results = rag_search(tenant_id, message, filter_folder_ids=knowledge_folders)
```

### 6.4 Требуется Tenant config read per-request

Уже есть `tenant = db.get(Tenant, tenant_id)` — config читается оттуда же.

---

## 7. Файлы (полный список)

| Файл | Действие | Описание |
|------|----------|----------|
| `api/app/models.py` | Изменить | + `Tenant.agent_config` JSONB |
| `api/app/agents/default_config.py` | **Новый** | `get_default_agent_config()` |
| `api/app/agents/base.py` | Изменить | + `intent: str \| None` в `AgentResult` |
| `api/app/agents/incoming_line.py` | Изменить | читать `tenant.agent_config` |
| `api/app/admin/agents.py` | Изменить | + все API роуты (секция 5); старые не трогать |
| `api/app/admin/pages.py` | Изменить | убрать `@router.get("/agents")` |
| `api/app/templates/agents_list.html` | **Новый** | карточки агентов |
| `api/app/templates/agent_detail.html` | **Новый** | 4 таба + playground |
| `api/alembic/versions/xxx_add_agent_config.py` | **Новый** | миграция |

---

## 8. Что НЕ делаем

- ❌ Inbox, Knowledge, Dashboard, Settings (их фазы)
- ❌ Бэкенд для Маркетолога и Контроля качества — только UI-карточки
- ❌ `ChatLog` → `AgentCall` — не нужно, статистика из `ChatLog`
- ❌ Управление папками Базы знаний — будет в Phase 4, сейчас только выбор существующих
- ❌ Роли/пермишены — будет в Phase 6
