# Incoming Line Agent — UI Design

## 1. User Roles & Goals

| Роль | Цель |
|------|------|
| **Админ клиники** | Видеть статистику работы агента, включить/выключить, настроить базовые параметры |
| **Оператор** | Видеть сколько эскалаций, быстро перейти в Inbox |

## 2. Структура

Одна страница: `/admin/agent-log`

Содержит:
- Stats bar (статистика работы агента)
- ON/OFF toggle (быстрое включение/выключение)
- Настройки (название клиники, часы работы, сообщения)

## 3. UI Mockup

```
┌──────────────────────────────────────────────────────────────┐
│  Agent Log                                                   │
│                                                              │
│  ┌──────────┬──────────┬──────────┬──────────┬─────────────┐ │
│  │  Today   │Escalated │Avg latency│  Total   │             │ │
│  │    47    │     3    │   1.2s   │  1,284   │ [● ON / OFF]│ │
│  └──────────┴──────────┴──────────┴──────────┴─────────────┘ │
│                                                              │
│  ┌─ Settings ───────────────────────────────────────────────┐│
│  │                                                          ││
│  │  Clinic name                                             ││
│  │  [Клиника ЛазерМед_____________________________]         ││
│  │                                                          ││
│  │  Business Hours                                          ││
│  │  Mon  [09:00 ☰]  —  [20:00 ☰]  [× Closed]              ││
│  │  Tue  [09:00 ☰]  —  [20:00 ☰]  [× Closed]              ││
│  │  Wed  [09:00 ☰]  —  [20:00 ☰]  [× Closed]              ││
│  │  Thu  [09:00 ☰]  —  [20:00 ☰]  [× Closed]              ││
│  │  Fri  [09:00 ☰]  —  [18:00 ☰]  [× Closed]              ││
│  │  Sat  [10:00 ☰]  —  [15:00 ☰]  [× Closed]              ││
│  │  Sun  [× Closed]                                        ││
│  │                                                          ││
│  │  Off-hours auto-reply                                    ││
│  │  [Мы сейчас закрыты. Позвоните нам в рабочее время     ]││
│  │  [с 9:00 до 20:00.____________________________________]││
│  │                                                          ││
│  │  When agent is disabled                                  ││
│  │  [Извините, онлайн-чат временно отключён. Пожалуйста,  ]││
│  │  [позвоните в клинику.________________________________]││
│  │                                                          ││
│  │  [Save]                                                  ││
│  └──────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
```

## 4. Stats Bar

4 карточки + toggle в одной строке:

| Метрика | Источник | Формат |
|---------|----------|--------|
| **Today** | `count(*) WHERE created_at >= today` | Число |
| **Escalated** | `count(*) WHERE escalate=true` | Число (красный если >0) |
| **Avg latency** | `avg(latency_ms)` | `1.2s` |
| **Total** | `count(*)` | Число |
| **Agent** | ON/OFF | Toggle |

Toggle меняет `enabled` в `agent_config` и сразу применяется (без Save).

## 5. Настройки

| Поле | Зачем | UI |
|------|-------|-----|
| Clinic name | Название в ответах агента | Text input |
| Business hours | Агент знает когда клиника работает | Сетка дней × время |
| Off-hours reply | Ответ когда клиника закрыта | Textarea |
| Disabled reply | Ответ когда агент выключен | Textarea |

Хранить в `Tenant.agent_config` (JSONB).

## 6. Поведение

| Состояние | Действие агента |
|-----------|----------------|
| ON + рабочее время | Нормальная работа |
| ON + нерабочее время | Ответить off-hours reply, escalate=true |
| OFF | Ответить disabled reply, escalate=true |

## 7. API

```
GET  /admin/api/agent-log/stats         → {today, escalated, avg_latency_ms, total}
GET  /admin/api/agent-log/settings      → {enabled, clinic_name, ...}
PUT  /admin/api/agent-log/settings      → сохранить настройки
POST /admin/api/agent-log/toggle        → {"enabled": bool}
```

## 8. Sidebar

Убрать Assistants/Campaigns. Добавить Agent Log.

Порядок: Inbox → Agent Log → Knowledge → Channels → Integrations → Compliance → Account

## 9. Implementation Order

1. Добавить `intent` в `AgentResult`, вернуть из `IncomingLineAgent.handle()`
2. Исправить channel handlers — `intent=result.intent`
3. Добавить `agent_config` колонку в `Tenant` (JSONB, ORM создаст сам)
4. API stats, settings, toggle
5. Страница Agent Log (stats + toggle + настройки на одной странице)
6. Sidebar cleanup

## 10. Что НЕ делаем

- ❌ Таблица лога вызовов
- ❌ Модалка с деталями
- ❌ Фильтры (intent, channel, date, search)
- ❌ Кнопка "Open in Inbox" / "Acknowledge"
- ❌ System prompt / RAG params в UI
- ❌ Не трогаем Inbox, Knowledge, Channels, Integrations
