# Jeeves — Test Plan

## Как пользоваться
1. Идти по модулям сверху вниз
2. Каждый сценарий: **Шаги → Ожидаемый результат → Pass/Fail**
3. Для интеграций где нет аккаунтов — использовать **mock-альтернативы** (указаны)
4. Базовый аккаунт: зарегистрироваться через `/admin/login` → Register

---

## 0. SETUP

### 0.1 Регистрация нового tenant
**Шаги:**
1. Открыть `/admin/login`
2. Переключиться на Register
3. Заполнить: company name, email, password (8+ chars)
4. Нажать Continue

**Ожидаемо:**
- Редирект на `/admin` (dashboard)
- В sidebar виден tenant name

---

## 1. AUTH (Standalone — не нужны внешние сервисы)

### 1.1 Login после регистрации
**Шаги:**
1. Выйти (Sign out в sidebar)
2. Войти с теми же credentials

**Ожидаемо:** Успешный вход, редирект на dashboard

### 1.2 Неверный пароль
**Шаги:** Войти с неправильным паролем

**Ожидаемо:** Ошибка "Invalid credentials"

### 1.3 API key auth (через curl/Postman)
**Шаги:**
1. Зайти на `/admin/api`
2. Сгенерировать ключ (дать имя "Test")
3. **Скопировать ключ** (покажется 1 раз)
4. Выполнить:
```bash
curl http://localhost:8000/chat \
  -H "Authorization: Bearer sk_..." \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test1","message":"hello"}'
```

**Ожидаемо:** JSON response с ответом от агента

### 1.4 Revoked API key
**Шаги:**
1. На `/admin/api` нажать Revoke у созданного ключа
2. Повторить curl из 1.3

**Ожидаемо:** 401 Unauthorized

### 1.5 Token refresh
**Шаги (через Postman/curl):**
1. Login → получить access_token и refresh_token
2. Подождать (или вручную истекший access_token)
3. POST `/auth/refresh` с refresh_token

**Ожидаемо:** Новая пара токенов

---

## 2. KNOWLEDGE BASE (нужен OpenAI API key)

### 2.1 Upload TXT файла
**Шаги:**
1. `/admin/knowledge`
2. Создать файл `test.txt` с контентом: `Вопрос: Как вернуть товар? Ответ: В течение 14 дней.`
3. Загрузить через drag-and-drop или browse

**Ожидаемо:**
- Файл появляется в таблице со статусом `processing` → `ready` (~10-60 сек)
- Внизу появляется test widget

### 2.2 Upload PDF файла
**Шаги:** Загрузить любой .pdf документ

**Ожидаемо:** Статус `processing` → `ready`

### 2.3 Upload неподдерживаемого формата
**Шаги:** Попробовать загрузить `.docx` или `.xlsx`

**Ожидаемо:** Файл не загружается или ошибка

### 2.4 Delete файла
**Шаги:** Нажать Delete у загруженного файла

**Ожидаемо:** Файл исчезает из таблицы

### 2.5 Widget появляется после KB ready
**Шаги:** Загрузить первый файл, подождать пока `ready`

**Ожидаемо:** В правом нижнем углу появляется chat widget

### 2.6 Agent отвечает на основе KB
**Шаги:**
1. Загрузить `test.txt` (2.1) и дождаться `ready`
2. Открыть widget
3. Написать: "Как вернуть товар?"

**Ожидаемо:** Агент отвечает "В течение 14 дней" или близко к этому

### 2.7 Несколько файлов
**Шаги:** Загрузить 2-3 файла с разной информацией

**Ожидаемо:** Все файлы в статусе `ready`, widget работает

---

## 3. CHAT (нужен OpenAI API key)

### 3.1 REST API chat (через API key)
**Шаги:**
```bash
curl http://localhost:8000/chat \
  -H "Authorization: Bearer sk_..." \
  -H "Content-Type: application/json" \
  -d '{"user_id":"cust_001","message":"Привет, помоги мне"}'
```

**Ожидаемо:**
```json
{
  "response": "...",
  "action_called": null,
  "latency_ms": 1234
}
```

### 3.2 Widget chat
**Шаги:**
1. Убедиться что KB ready (файл загружен)
2. Открыть `/admin/widget-preview` или вставить snippet на любую страницу
3. Написать сообщение

**Ожидаемо:** Ответ от агента в виджете

### 3.3 Chat без KB (fallback)
**Шаги:**
1. Удалить все KB файлы
2. Написать в widget

**Ожидаемо:** Агент отвечает (использует системный промпт), но без sourcing

### 3.4 Эскалация
**Шаги:** Написать что-то что агент не может решить (намеренно ambiguous)

**Ожидаемо:** В response может быть escalation, в logs resolution = "escalated"

### 3.5 Long conversation (memory)
**Шаги:** Написать 5+ сообщений подряд в widget

**Ожидаемо:** Агент помнит контекст предыдущих сообщений

---

## 4. CHANNELS

### 4.1 Website Widget — настройка
**Шаги:**
1. `/admin/channels` → Website Widget (выбран по умолчанию)
2. Изменить title, subtitle, greeting, accent color
3. Проверить что install snippet обновляется в реальном времени
4. Нажать Copy

**Ожидаемо:**
- Snippet обновляется при каждом изменении
- Clipboard содержит валидный `<script>` тег

### 4.2 Website Widget — установка
**Шаги:**
1. Скопировать snippet
2. Создать `test.html` на любом сайте/локально:
```html
<html><body>
<script async src="http://localhost:8000/widget.js" data-tenant-id="YOUR_TENANT_ID"></script>
</body></html>
```
3. Открыть в браузере

**Ожидаемо:** Floating chat button появляется в углу

### 4.3 Telegram — setup (нужен Telegram аккаунт)
**Mock-альтернатива:** Пропустить если нет Telegram Bot token

**Реальный тест (если есть):**
1. Найти @BotFather в Telegram
2. `/newbot` → получить token
3. `/admin/channels` → Telegram
4. Вставить token → Save & Test

**Ожидаемо:** Badge → "connected"

### 4.4 WhatsApp — setup (нужен Meta Developer аккаунт)
**Mock-альтернатива:** Пропустить — требует WhatsApp Business API approval

**Если есть sandbox:**
1. Meta Developers → WhatsApp → получить Phone Number ID + Access Token
2. Заполнить в UI → Save & Test

---

## 5. CRM INTEGRATIONS (Test CRM на порту 8001)

**Pre-requisite:** Запустить Test CRM: `cd test-crm && uvicorn test_crm_app:app --port 8001`

### 5.1 Подключение Test CRM — Read
**Шаги:**
1. `/admin/integrations` → CRM → Custom REST API
2. API endpoint: `http://localhost:8001/customers/{user_id}`
3. Fields for Jeeves: `plan`, `status`, `mrr`, `orders_count`, `name`, `email`, `company`
4. Нажать Test (user_id: `cust_alice_001`)

**Ожидаемо:**
- Test показывает полный JSON с данными Alice Johnson (enterprise, active, $499 MRR)
- Badge → "Custom REST" (ok)

### 5.2 Подключение Test CRM — Write (update plan)
**Шаги:**
1. Write URL: `http://localhost:8001/customers/{user_id}/plan`
2. Capability "Изменение плана / тарифа" — checkbox
3. Capability "Спрашивать подтверждение перед записью" — checkbox
4. Save → Test

**Ожидаемо:** Сохранено, badge ok

### 5.3 Customer lookup через chat
**Шаги:**
1. Убедиться что CRM настроен (5.1)
2. Открыть widget
3. Написать: "What plan am I on?" или "Какой у меня план?"
4. Использовать user_id: `cust_alice_001`

**Ожидаемо:** Агент отвечает что у пользователя enterprise plan, company TechCorp Inc.

### 5.4 Order lookup через chat (дополнительный endpoint)
**Шаги:**
1. В CRM → добавить поле `orders_count` в mapping
2. Написать в widget: "How many orders do I have?" (user_id: `cust_alice_001`)

**Ожидаемо:** Агент отвечает 23 orders

### 5.5 Update plan через chat (write action)
**Шаги:**
1. Убедиться что Write URL настроен и capability "update_plan" включена
2. Написать в widget: "Change my plan to enterprise" (user_id: `cust_bob_002` — у него business)
3. Агент должен спросить подтверждение → ответить "yes"

**Ожидаемо:**
- План обновлён (проверить в `/admin/integrations` → Test или в Test CRM UI на :8001)
- Agent подтвердил изменение

### 5.6 Test CRM UI
**Шаги:**
1. Открыть `http://localhost:8001`
2. Проверить таблицу Customers — 15 записей
3. Переключиться на Orders tab

**Ожидаемо:**
- 15 customers с разными планами/статусами
- Orders с разными статусами
- Данные реалистичные (имена, компании, MRR)

### 5.7 Filter customers
**Шаги (curl/Postman):**
```bash
curl "http://localhost:8001/customers?status=active&plan=business"
```

**Ожидаемо:** Только business-план с active статусом

### 5.8 HubSpot (нужен HubSpot аккаунт)
**Mock-альтернатива:** Пропустить — Test CRM покрывает все сценарии

**Если есть:**
1. CRM → HubSpot tab → Connect HubSpot
2. OAuth flow → authorize
3. Badge → "connected"

---

## 6. E-COMMERCE INTEGRATIONS (Native Connectors)

### 6.1 Shopify (нужен Shopify store)
**Mock-альтернатива:** Пропустить

**Если есть:**
1. Integrations → E-commerce → Shopify
2. Shop domain + Admin API token
3. Connect → Test

**Ожидаемо:** Badge "connected", auto-provisioned tools в `/admin/tools`

### 6.2 WooCommerce (нужен Woo store)
**Mock-альтернатива:** Пропустить

### 6.3 Stripe (нужен Stripe аккаунт)
**Mock-альтернатива:** Можно использовать Stripe test mode (`sk_test_...`)

**Если есть test key:**
1. Integrations → E-commerce → Stripe
2. Secret API key: `sk_test_...`
3. Connect → Test

---

## 7. AGENT TOOLS

### 7.1 Создание Lookup tool
**Шаги:**
1. `/admin/tools` → + Add tool
2. Name: `get_mock_order`
3. Type: Lookup
4. Method: GET
5. URL: `http://localhost:8000/mock/orders/{order_id}`
6. Auth headers: `{}`
7. Parameters: `{"order_id":{"type":"string","description":"Order ID to look up"}}`
8. Save

**Ожидаемо:** Tool в таблице, статус enabled

### 7.2 Test tool
**Шаги:** Нажать Edit → Test у созданного tool

**Ожидаемо:** Response от mock endpoint

### 7.3 Создание Action tool
**Шаги:**
1. + Add tool
2. Name: `create_mock_ticket`
3. Type: Action
4. Method: POST
5. URL: `http://localhost:8000/mock/tickets`
6. Parameters: `{"subject":{"type":"string","description":"Ticket subject"}}`
7. Require confirmation: checked
8. Save

**Ожидаемо:** Tool в таблице с pill "action"

### 7.4 Toggle tool on/off
**Шаги:** Выключить checkbox у tool

**Ожидаемо:** Tool disabled, не вызывается агентом

### 7.5 Delete tool
**Шаги:** Delete у tool

**Ожидаемо:** Tool удалён из таблицы

### 7.6 Tool logs
**Шаги:** После тестирования tools, проверить "Recent tool calls"

**Ожидаемо:** Записи с tool name, status, latency

---

## 8. PROACTIVE ENGINE (Test CRM на порту 8001)

### 8.1 Настройка с Test CRM activity endpoint
**Шаги:**
1. `/admin/proactive`
2. Metric URL: `http://localhost:8001/activity/{id}`
3. Threshold: 30%
4. Save

**Ожидаемо:** Saved confirmation

### 8.2 Proactive message для at-risk customer
**Шаги:**
1. Настроить proactive (8.1)
2. Celery worker должен запустить proactive check (каждый час)
3. Customer `cust_jack_010` имеет declining activity: 8→6→5→3→2→1→0
4. Сегодня 0 logins vs 3-day average ~2 → падение >30%
5. Jeeves должен отправить proactive message в inbox

**Проверка:**
```bash
curl "http://localhost:8000/widget/inbox?tenant_id=YOUR_TENANT_ID&user_id=cust_jack_010"
```

**Ожидаемо:** Сообщение в inbox (delivered=false)

### 8.3 No proactive for active customers
**Шаги:** Customer `cust_alice_001` имеет стабильную активность

**Ожидаемо:** No proactive message (activity не упала)

### 8.4 No proactive for churned customer
**Шаги:** Customer `cust_frank_006` (churned, zero activity)

**Ожидаемо:** No proactive message (уже churned, не стоит беспокоить)

---

## 9. DASHBOARD

### 9.1 Stats загружаются
**Шаги:** Открыть `/admin`

**Ожидаемо:**
- Dialogs today, Resolved today, Resolution rate — числа (могут быть 0)
- Avg response time, Total dialogs, Overall resolution

### 9.2 Trend chart (7 дней)
**Шаги:** Написать несколько сообщений в widget

**Ожидаемо:** На графике появляются данные

### 9.3 Peak hours chart
**Шаги:** После нескольких диалогов

**Ожидаемо:** Гистограмма по часам

### 9.4 Channels breakdown
**Шаги:** После диалогов через разные каналы

**Ожидаемо:** Progress bars по каналам (если только widget — один bar)

### 9.5 Recent unresolved
**Шаги:** Если были эскалации

**Ожидаемо:** Список unresolved conversations

### 9.6 Getting Started — conditional
**Шаги:**
1. Новый tenant без KB → Getting Started показывает "Upload knowledge base"
2. Загрузить KB файл → Getting Started обновляется, показывает следующий шаг
3. Настроить всё → Getting Started исчезает

**Ожидаемо:** Показывает только незавершённые шаги

---

## 10. CHAT LOGS

### 10.1 Просмотр логов
**Шаги:** `/admin/logs`

**Ожидаемо:**
- Таблица с conversations (time, user, direction, message, response, resolution, ms)
- Sources раскрываются (если KB использовался)

### 10.2 Filter by user_id
**Шаги:** Ввести user_id в фильтр → Search

**Ожидаемо:** Только сообщения этого пользователя

### 10.3 Filter by days
**Шаги:** Изменить days на 1, 7, 30

**Ожидаемо:** Фильтрация по дате работает

---

## 11. BILLING

### 11.1 Usage stats
**Шаги:** `/admin/billing`

**Ожидаемо:**
- Dialogs used: число
- Trial limit: 100
- Resolution rate: %
- Trial ends: дата
- Estimated charge: $X.XX

### 11.2 Trial enforcement
**Шаги (если dialogs >= 100):**
1. Написать в widget

**Ожидаемо:** 402 Payment Required

---

## 12. WEBHOOKS (нужен webhook receiver)

### 12.1 Outgoing webhook config
**Шаги:**
1. `/admin/integrations` → Webhooks & Writeback (coming soon — skip если disabled)
2. Если доступно: настроить outgoing_url на `https://webhook.site/xxx`

**Ожидаемо:** Webhook fires на события (conversation.ended и тд)

---

## 13. WRITEBACK (нужен HubSpot или webhook receiver)

### 13.1 Webhook writeback
**Шаги:**
1. Если доступно: type=webhook, webhook_url=`https://webhook.site/xxx`
2. Завершить conversation

**Ожидаемо:** POST с summary на webhook URL

---

## Pre-requisites для тестирования

```bash
# 1. Запустить основной Jeeves (порт 8000)
# docker compose up  или  uvicorn app.main:app --port 8000

# 2. Запустить Test CRM (порт 8001)
cd test-crm
uvicorn test_crm_app:app --host 0.0.0.0 --port 8001 --reload

# 3. Убедиться что Celery worker запущен (для proactive, indexing)
celery -A worker.tasks worker --loglevel=info
```

## Сводная таблица

| # | Модуль | Тестов | Зависимости | Mock available |
|---|--------|--------|-------------|----------------|
| 0 | Setup | 1 | Нет | ✅ |
| 1 | Auth | 5 | Нет | ✅ |
| 2 | Knowledge | 7 | OpenAI | ❌ (нужен API key) |
| 3 | Chat | 5 | OpenAI | ❌ (нужен API key) |
| 4 | Channels | 4 | Нет (widget standalone) | ✅ |
| 5 | CRM | 8 | Test CRM (:8001) | ✅ Test CRM included |
| 6 | E-commerce | 3 | Shopify/Woo/Stripe (optional) | ❌ |
| 7 | Tools | 6 | Нет | ✅ |
| 8 | Proactive | 4 | Test CRM (:8001) + Celery | ✅ Test CRM included |
| 9 | Dashboard | 6 | Нет | ✅ |
| 10 | Logs | 3 | Нет | ✅ |
| 11 | Billing | 2 | Нет | ✅ |
| 12 | Webhooks | 1 | webhook.site (optional) | ✅ |
| 13 | Writeback | 1 | HubSpot/webhook (optional) | ✅ |
| | **Итого** | **56** | | |

## Критерий приёмки (MVP)

**Обязательные (должны пройти):**
- [ ] 0.1 Регистрация работает
- [ ] 1.1 Login работает
- [ ] 1.3 API key auth работает
- [ ] 2.1 Upload KB файла → статус ready
- [ ] 2.6 Agent отвечает на основе KB (через widget)
- [ ] 3.1 REST API chat работает
- [ ] 3.2 Widget chat работает
- [ ] 4.1 Widget snippet генерируется
- [ ] 4.2 Widget появляется на странице
- [ ] 5.1 Test CRM подключен — read customer данные
- [ ] 5.2 Test CRM — update plan (write)
- [ ] 5.3 Agent видит CRM данные в чате ("какой у меня план?")
- [ ] 5.5 Agent обновляет план через chat
- [ ] 7.1-7.5 CRUD tools работает
- [ ] 8.1 Proactive с Test CRM activity настроен
- [ ] 9.1 Dashboard stats загружаются
- [ ] 9.6 Getting Started conditional
- [ ] 10.1 Logs показывают conversations
- [ ] 11.1 Billing stats показываются

**Опциональные (nice to have, можно пропустить):**
- [ ] 4.3 Telegram
- [ ] 4.4 WhatsApp
- [ ] 5.7 HubSpot
- [ ] 6.1-6.3 E-commerce connectors
- [ ] 12.1 Outgoing webhooks
- [ ] 13.1 Writeback
