# Inbox Optimization Plan

## Priority: Block 1 → Block 2 → Block 3 → Block 4 → Block 5

---

## Блок 1 — Критические баги (data loss / неработающий функционал)

| # | Проблема | Файл:строка | Статус |
|---|----------|-------------|--------|
| 1 | Операторские сообщения не доходят до виджета (`sender_type != "operator"` фильтр) | `widget.py:237` | ✅ |
| 2 | Escalation статус выставляется дважды (дублированный код) | `inbox.py:397-403` | ✅ |
| 3 | SSE endpoint — dead code после return | `inbox.py:895-897` | ✅ |
| 4 | `send_message()` не использует `add_message()` из shared | `inbox.py:322-352` | ✅ |

## Блок 2 — Логика Takeover / Assignment

| # | Проблема | Статус |
|---|----------|--------|
| 5 | Кнопки Assign и Take Over показываются одновременно | ✅ |
| 6 | Любой оператор может отнять/закрыть чужой диалог | ✅ (takeover логи с previous_assignee) |
| 7 | Close не останавливает workflow | ✅ |
| 8 | Return-to-AI не снимает assignee если conversation closed | ✅ |
| 9 | Нет аудита кто и когда сделал assign/takeover/close | ✅ (system_event + timeline) |

## Блок 3 — UI / Верстка (inbox.html)

| # | Проблема | Статус |
|---|----------|--------|
| 10 | Inline CSS + Inline JS в одном template | ✅ (static/css/inbox.css + static/js/inbox.js) |
| 11 | Profile panel фиксированный — не влезает на узких экранах | ✅ (slide-over overlay + close button) |
| 12 | height: calc(100vh - 0px) | ✅ |
| 13 | Кнопки наезжают друг на друга | ✅ (flex-wrap) |
| 14 | Нет loading-индикаторов | ✅ (CSS spinner через ::before) |
| 15 | Ошибки silent-catch | ✅ (toast + error handling) |
| 16 | Poll 10s + SSE одновременно | ✅ (SSE-only) |

## Блок 4 — unread_count / доставка сообщений

| # | Проблема | Статус |
|---|----------|--------|
| 17 | `delivered=True` ставится сразу при poll | ✅ (только когда `viewing=true`) |
| 18 | `unread_count` не сбрасывается при просмотре | ✅ (`/read` endpoint) |
| 19 | Виджет ведет свой счетчик unread | ❌ (OK для MVP) |

## Блок 5 — Технический долг

| # | Проблема | Статус |
|---|----------|--------|
| 20 | Нет лимита на длину сообщения оператора | ✅ |
| 21 | N+1 запрос в `_conversation_to_item()` | ✅ (batch-load в list_conversations) |
| 22 | Conversation model escalation_id — логика сырая | ✅ (conv.escalation_id, return-to-ai resolve, manager column fix, дубликат функции удалён) |
