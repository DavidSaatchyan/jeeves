# UI для Incoming Line Agent — План работ

## 1. Контекст

Только UI для агента «Входящая линия». Ничего не трогаем из существующих страниц (Inbox, Knowledge, Channels, Integrations, Settings, Compliance, Account).

Из сайдбара убрать только мёртвые ссылки на удалённые воркфлоу:
- Секция «Assistants» → Marketing Funnel, Patient Follow-up — удалены вместе с `core/workflows/`
- Campaigns (`/admin/marketing`) — удалён

Всё остальное в сайдбаре остаётся без изменений.

## 2. Что пользователь должен видеть для Incoming Line

### Agent Call Log (главное)
Таблица всех вызовов агента:
- Время, пациент, сообщение, intent, ответ (обрезанный), статус (escalated/ok), latency
- Клик по строке → модалка с полным диалогом
- Фильтры: по дате, по intent, только escalated

### Escalations
Отфильтрованный лог, где `escalate=true`:
- Требуют внимания оператора
- Полный контекст переписки

### Статус агента
Мини-дашборд сверху:
- Сколько обработано сегодня / всего
- Средняя latency
- Сколько escalated

### Конфигурация (view-only)
Показать текущие настройки агента из config.yaml:
- Модель, температуры, system prompt
- RAG params (top_k, threshold)
- Без редактирования

## 3. План реализации

### Шаг 1: Сайдбар
- Убрать секцию «Assistants» (Marketing Funnel, Patient Follow-up)
- Убрать ссылку Campaigns
- Добавить пункт «Agent Log» в навигацию
- *(Inbox, Knowledge, Channels, Integrations, Compliance, Settings, Account — остаются)*

### Шаг 2: API для Agent Call лога
- `GET /admin/api/agent-calls` — список с пагинацией, фильтрацией
- `GET /admin/api/agent-calls/stats` — статистика

### Шаг 3: Страница Agent Log
- Таблица на Jinja2 + vanilla JS
- Фильтры: дата, intent, escalated
- Модалка с деталями

### Шаг 4: Страница конфигурации (view-only)
- Показать текущий конфиг агента из `config.yaml`

## 4. Какие файлы меняем

| Файл | Действие |
|------|----------|
| `templates/base.html` | Убрать Assistants/Campaigns, добавить Agent Log |
| `admin/pages.py` | Добавить `/admin/agent-log` роут |
| `admin/pages.py` | Добавить API `/admin/api/agent-calls` |
| `templates/agent_log.html` | Новая страница |

## 5. Что НЕ делаем
- Не трогаем Inbox, Knowledge, Channels, Integrations и т.д.
- Никаких новых агентов (scheduler, followup, ops)
- Никакого редактора конфига — только просмотр
