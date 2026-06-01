# Phase 7: UI Reframe — Medical Clinic Terminology

> **Дата:** 2026-05-31
> **Базовый документ:** REBRAND-MEDICAL.md (Phase 7: Days 28–30)
> **Время:** ~3 дня
> **Ограничение:** `landing.html` не трогаем (переписывается отдельно)

---

## 1. Цель

Переписать UI-шаблоны и admin-панель для медицинской клиники: заменить e-commerce/Shopify терминологию на медицинскую, добавить новые страницы (Compliance Dashboard, Appointments), обновить навигацию.

### Что меняем

| Страница | Действие | Причина |
|----------|----------|---------|
| `base.html` | Update branding + nav | "AI Support Agent" → "AI Communication & Support", sidebar: новые агенты |
| `agents.html` | Rewrite — medical agents | WISMO/Assist → Appointment Manager + Marketing + Follow-up |
| `connections.html` | Minor update | Уже переписан на CRM — только фикс терминологии |
| `knowledge.html` | Reframe catalog | "Product Catalog" → "Services Catalog", SKU/price/stock → procedure/service |
| `compliance.html` | Rewrite | Bootstrap stub → полноценный dark-theme дашборд |
| `appointments.html` | CREATE | Новый календарь + управление слотами (back-end уже есть) |
| `channels.html` | Minor update | Email channel → WhatsApp + Widget |
| `inbox.html` | Terminology pass | Заменить "order"/"customer" на "patient"/"visit" |

### Что НЕ трогаем
- `landing.html` — отложено
- `login.html` — минимальные изменения, только логотип
- `account.html`, `settings.html`, `privacy.html`, `terms.html` — только терминология

---

## 2. Текущее состояние (AS-IS)

### Что уже есть

| Компонент | Файл | Статус |
|-----------|------|--------|
| Base template | `templates/base.html` | **Есть** — "AI Support Agent", sidebar: Inbox, Knowledge, Channels, Connections, Assist |
| Agents page | `templates/agents.html` | **Есть** — только один "Assist" агент (старый e-commerce WISMO) |
| Connections page | `templates/connections.html` | **Есть** — уже переписан на CRM (Zoho, HubSpot, Custom API) |
| Knowledge page | `templates/knowledge.html` | **Есть** — Documents + Product Catalog (SKU/price/stock) |
| Compliance page | `templates/compliance.html` | **Есть** — Bootstrap-заглушка, не использует base.html стили |
| Channels page | `templates/channels.html` | **Есть** — старая версия с Email + Widget |
| Inbox page | `templates/inbox.html` | **Есть** — e-commerce терминология (order, customer, tracking) |
| Appointments page | `templates/appointments.html` | **НЕТ** |
| Admin API (compliance) | `admin/compliance.py` | **Есть** — 10 endpoints (consent, audit, retention, summary) |
| Admin API (appointments) | `admin/appointments.py` | **Есть** — CRUD appointments |
| Admin API (agents) | `admin/agents.py` | **Есть** — workflow policies |
| Admin API (workflows) | `admin/workflows.py` | **Есть** — список workflow |

### Чего нет / что плохо

| Компонент | Проблема |
|-----------|----------|
| `appointments.html` | **НЕТ** — backend есть, UI нет |
| `compliance.html` | Bootstrap-заглушка — не вписывается в дизайн |
| `agents.html` | Только один агент "Assist" — нет Appointment Manager, Marketing, Follow-up |
| `knowledge.html` | "Product Catalog" — e-commerce (SKU, price, stock, currency) |
| `base.html` | Branding: "AI Support Agent", нет nav для новых разделов |
| Sidebar | Нет ссылок на Appointments, Compliance, Marketing campaigns |
| Терминология | "customer", "order", "tracking", "product", "billing" — всё e-commerce |

---

## 3. Архитектура (TO-BE)

### Целевая навигация

```
Sidebar:
├── Inbox                    # Conversations with patients
├── Appointments  (NEW)      # Calendar + slot management
├── Knowledge                # Documents + Services Catalog
├── Channels                 # WhatsApp + Widget
├── Connections              # CRM integrations (Zoho, HubSpot, Salesforce)
│
├── ═══ Assistants ═══
├── Appointment Manager      # Booking workflow agent
├── Marketing Funnel         # Campaign agent (NEW)
├── Patient Follow-up        # Post-visit agent (NEW)
│
├── Campaigns     (NEW)      # Marketing campaign management
├── Compliance    (NEW)      # Consent + audit dashboard
│
├── Account
└── Sign out
```

### Dependency Direction

```
templates/*.html → admin/*.py API endpoints  (ALLOWED)
templates/base.html → extends all pages       (ALLOWED)

FORBIDDEN:
templates/ → core/, channels/, integrations/  (templates NEVER call backend directly)
```

### Terminology Mapping

| Old (e-commerce) | New (medical) |
|------------------|---------------|
| customer | patient |
| order | visit / appointment |
| tracking / WISMO | follow-up / post-visit |
| product | service / procedure |
| SKU | procedure code |
| price | fee / cost estimate |
| stock | availability |
| billing / subscription | insurance / payment |
| shop / store | clinic |
| support agent | care team |
| AI Assistant | AI Patient Assistant |
| ticket / inquiry | patient inquiry / message |

---

## 4. Задачи

### 4.1. Обновить `templates/base.html` — Branding + Navigation

**Изменения:**
1. Brand name: "AI Support Agent" → "AI Communication & Support"
2. Sidebar: добавить новые пункты навигации:
   - **Appointments** — между Inbox и Knowledge
   - **Campaigns** — после Assistants секции
   - **Compliance** — после Campaigns
3. Assistants секция: 3 агента вместо 1:
   - Appointment Manager (иконка календаря)
   - Marketing Funnel (иконка воронки)
   - Patient Follow-up (иконка пульса)
4. Обновить badge counter logic

**Проверка:**
- `base.html` рендерится без ошибок Jinja2
- Все существующие `{% extends "base.html" %}` страницы работают

---

### 4.2. Переписать `templates/agents.html` — Medical Agents

**Текущее:** Один "Assist" агент с WISMO-подобными состояниями.

**Цель:** Три агента с реальными данными из workflow registry:

| Agent | Workflow Type | States |
|-------|--------------|--------|
| Appointment Manager | `appointment` | AWAITING_INTENT, CHECKING_SCHEDULE, OFFERING_SLOTS, CONFIRMING, BOOKED, REMINDER_SENT, ARRIVED, NO_SHOW, COMPLETED, CANCELLED |
| Marketing Funnel | `marketing` | LEAD_CAPTURED, QUALIFYING, NURTURING, APPOINTMENT_BOOKED, FOLLOW_UP, CONVERTED, LOST |
| Patient Follow-up | `followup` | VISIT_COMPLETED, DAY_1_CHECK, DAY_7_CHECK, DAY_30_CHECK, MEDICATION_ADHERENCE, SATISFACTION_SURVEY, CLOSED |

**Изменения в JS:**
- Заменить `var AGENT = { id:'assist', ... }` на массив из 3 агентов
- `renderAll()` → принимает `workflows` и группирует по `workflow_type`
- Каждый агент получает свой `renderAgentPanel()` с фильтром по `workflow_type`
- Toggle enable/disable через `policies.enabled_workflows` (существующий API)

**API endpoint:** `GET /admin/api/workflows?limit=500` (уже есть)

**Структура рендера:**
```html
<div class="ch-tabs">
  <button class="ch-tab active" data-agent="appointment">Appointment Manager</button>
  <button class="ch-tab" data-agent="marketing">Marketing Funnel</button>
  <button class="ch-tab" data-agent="followup">Patient Follow-up</button>
</div>
<div id="agentPanels"> // 3 panels, one per agent </div>
```

**Проверка:**
- 3 вкладки с各自ными KPI (total, active, completed, escalated)
- State distribution показывает только состояния для данного типа workflow
- Policy settings загружаются и сохраняются

---

### 4.3. Обновить `templates/connections.html` — CRM Config UI

**Текущее:** Уже переписан на CRM (Zoho, HubSpot, Custom API) — секции, поля, webhook config.

**Изменения:**
- Добавить Salesforce как четвёртый провайдер (если не добавлен)
- Обновить описания: "PHI-safe" → "BAA-compatible" и т.д.
- Добавить кнопку "Sync now" для каждого активного соединения
- Добавить секцию "Last sync" с датой

**Проверка:**
- Все 3-4 CRM провайдера отображаются
- Connect/test/disconnect работают
- Webhook URL копируется

---

### 4.4. Переписать `templates/knowledge.html` — Services Catalog

**Текущее:** "Product Catalog" с SKU, price, stock, currency (USD), import batch.

**Цель:** "Services Catalog" для медицинских услуг:

```
Services Catalog:
├── Procedure name     (was: Product name)
├── Procedure code     (was: SKU)
├── Department         (NEW: Cardiology, Dermatology, etc.)
├── Duration (min)     (NEW: 30, 60, 90 min)
├── Fee estimate       (was: Price — still a number, but label changes)
├── Availability       (was: Stock — in_stock → available, out_of_stock → unavailable)
└── Description        (was: Attributes — already exists)
```

**Изменения:**
1. Tab label: "Product Catalog" → "Services Catalog"
2. Table columns: Name, Code, Department, Duration, Fee, Availability, Batch
3. Modal: "Attributes" → "Details", remove "Stock status" badge, add Department
4. Upload: .csv/.json/.xlsx → .csv/.json (accept medical service data)
5. All JS references: "product" → "service", "import" → "upload"
6. Text: "No products yet" → "No services yet"

**Проверка:**
- Services catalog tab отображается с новыми колонками
- Upload CSV с сервисами работает
- Detail modal показывает длительность, департамент, описание

---

### 4.5. Создать `templates/compliance.html` — Compliance Dashboard

**Текущее:** Bootstrap-заглушка (25 строк, не использует base.html).

**Цель:** Полноценный dark-theme дашборд в стиле base.html:

**Секции:**

1. **Summary Cards** (stat cards style):
   - Total patients
   - Consented (marketing + appointment)
   - Consent rate %
   - Audit events today

2. **Consent Management Tab:**
   - Поиск пациента
   - Текущий статус consent (granted/revoked/expired)
   - Кнопки Grant / Revoke
   - История изменений

3. **Audit Log Tab:**
   - Таблица логов с фильтрами: action, date range, patient
   - Export to CSV кнопка
   - Пагинация

4. **Retention Policy Tab:**
   - Текущие настройки retention per data type
   - Apply retention policy кнопка
   - Purge expired data кнопка

**API endpoints (уже есть):**
- `GET /api/compliance/summary`
- `GET /api/compliance/patients/{id}/consent`
- `POST /api/compliance/patients/{id}/consent`
- `POST /api/compliance/patients/{id}/consent/revoke`
- `GET /api/compliance/audit-logs`
- `GET /api/compliance/audit/export`
- `GET /api/compliance/retention/settings`
- `POST /api/compliance/retention/apply`
- `POST /api/compliance/retention/purge`

**Проверка:**
- 3 вкладки: Consent, Audit Logs, Retention
- Summary cards загружаются при открытии
- Consent search + grant/revoke работают
- Audit log таблица + фильтры + export
- Retention apply + purge работают

---

### 4.6. Создать `templates/appointments.html` — Calendar + Booking UI

**Цель:**全新 страница управления приёмами.

**Секции:**

1. **Date Navigator + Calendar View:**
   - Day / Week / Month переключение
   - Навигация по датам (← today →)
   - Цветовая индикация: confirmed (green), completed (blue), cancelled (red), no_show (amber)

2. **Appointments List:**
   - Таблица или card list: time, patient name, provider, reason, status
   - Фильтры: date, provider, status
   - Пагинация

3. **Create Appointment Modal:**
   - Patient search
   - Provider select
   - Date/time picker
   - Reason/notes field
   - Source: admin

4. **Appointment Detail Modal:**
   - Полная информация о приёме
   - Кнопки: Confirm, Cancel, Mark No-Show, Mark Completed, Reschedule
   - Timeline (workflow state history)

**API endpoints (уже есть):**
- `GET /api/appointments` — list with filters
- `POST /api/appointments` — create
- `PUT /api/appointments/{id}` — update status
- `DELETE /api/appointments/{id}` — cancel

**Проверка:**
- Calendar view отображает appointments по датам
- Create appointment modal открывается и создаёт запись
- Status update (confirm/cancel/no-show/completed) работает
- Фильтры работают

---

### 4.7. Update Terminology in All Templates

**Файлы для терминологического обновления:**

| Файл | Что меняем |
|------|-----------|
| `templates/inbox.html` | "customer" → "patient", "order" → "visit"/"appointment", "tracking" → "follow-up" |
| `templates/channels.html` | "Email" channel → убрать, "Widget" → "Website Widget", "WhatsApp" → выделить как primary |
| `templates/account.html` | "Shop" → "Clinic", "Billing" → "Subscription" |
| `templates/settings.html` | "Store settings" → "Clinic settings", убрать Shopify-ссылки |
| `admin/agents.py` | Терминология в API ответах |
| `admin/appointments.py` | Терминология в API ответах |

**Глобальные замены:**
- "customer" (в контексте пациента) → "patient"
- "order" (в контексте клиники) → "visit" или "appointment"
- "shop" → "clinic"
- "store" → "clinic"
- "AI Support Agent" → "AI Communication & Support Platform"

**Проверка:**
- Ни одна страница не содержит "Shopify", "WISMO", "e-commerce" в видимом тексте
- Все упоминания "customer" заменены на "patient" (где уместно)

---

### 4.8. Обновить `admin/__init__.py` — Router Registration

Проверить, что все новые admin роутеры зарегистрированы:

```python
from . import (
    agents, analytics, appointments, compliance, inbox,
    integrations, logs, marketing, pages, policies, settings, workflows
)
```

✅ Уже есть (из Phase 2-6).

---

## 5. Порядок выполнения

| Шаг | Задача | Файлы | Проверка |
|-----|--------|-------|----------|
| 1 | Обновить `base.html` — branding + nav | `templates/base.html` | `{% extends "base.html" %}` работает на всех страницах |
| 2 | Переписать `agents.html` — 3 medical agents | `templates/agents.html` | 3 вкладки с各自ными KPI и состояниями |
| 3 | Обновить `connections.html` — Salesforce + sync | `templates/connections.html` | Все CRM провайдеры работают |
| 4 | Переписать `knowledge.html` — Services Catalog | `templates/knowledge.html` | Catalog показывает medical services |
| 5 | Создать `appointments.html` — Calendar UI | `templates/appointments.html` | Calendar + CRUD appointments |
| 6 | Переписать `compliance.html` — Dashboard | `templates/compliance.html` | Consent + Audit + Retention tabs |
| 7 | Update terminology in `inbox.html` | `templates/inbox.html` | Нет e-commerce терминов |
| 8 | Update terminology in `channels.html` | `templates/channels.html` | WhatsApp primary, Email removed |
| 9 | Update terminology in `account.html`, `settings.html` | `templates/account.html`, `templates/settings.html` | Clinic terminology |
| 10 | Финальная проверка | — | `from app.main import app` — 0 ошибок; все страницы рендерятся |

---

## 6. Definition of Done

1. `base.html` — brand: "AI Communication & Support Platform", sidebar: Inbox, Appointments (NEW), Knowledge, Channels, Connections, Assistants (3 agents), Campaigns, Compliance, Account
2. `agents.html` — 3 tabbed agent panels: Appointment Manager, Marketing Funnel, Patient Follow-up — каждый с KPI, state distribution, policy settings
3. `connections.html` — 4 CRM providers (Zoho, HubSpot, Salesforce, Custom API) с Connect/Test/Disconnect/Sync Now
4. `knowledge.html` — Documents + Services Catalog (procedure code, department, duration, fee, availability вместо SKU/price/stock)
5. `appointments.html` — calendar view (day/week/month) + CRUD модалки + фильтры
6. `compliance.html` — полноценный dark-theme дашборд: Consent management, Audit logs (с фильтрами + export), Retention policy
7. `inbox.html` — "customer" → "patient", "order" → "visit", "tracking" → "follow-up"
8. `channels.html` — WhatsApp как primary channel, Widget как secondary, Email убран
9. `account.html`, `settings.html` — clinic-терминология, без Shopify
10. `from app.main import app` — 0 ошибок импорта
11. Все страницы открываются в браузере без JS-ошибок

---

## 7. Структура файлов после Phase 7

```
api/app/templates/
├── base.html                 # 🔄 Branding + nav + 3 agents + новые разделы
├── account.html              # 🔄 Terminology: shop → clinic
├── agents.html               # 🔄 Rewrite: 3 medical agents
├── appointments.html         # NEW — Calendar + booking UI
├── channels.html             # 🔄 WhatsApp primary, Widget secondary
├── compliance.html           # 🔄 Rewrite: dark-theme dashboard
├── connections.html          # 🔄 Minor: +Salesforce +Sync Now
├── inbox.html                # 🔄 Terminology: patient/visit
├── knowledge.html            # 🔄 Service Catalog вместо Product Catalog
├── landing.html              # ⛔ Не трогаем
├── login.html                # ✅ Minor (logo only)
├── privacy.html              # ✅ Minor
├── settings.html             # 🔄 Terminology: clinic settings
└── terms.html                # ✅ Minor

api/app/templates/ (NEW files)
└── (none — все новые страницы уже в списке выше)
```

---

## 8. Риски

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| `base.html` изменения ломают `{% extends %}` на других страницах | Средняя | Проверить каждую страницу после изменения base.html |
| `agents.html` — 3 вкладки грузят много данных (500+ workflows) | Низкая | Фильтр по `workflow_type` на backend + limit/page |
| `compliance.html` — сложный дашборд с 3 вкладками | Средняя | По одной вкладке за раз; lazy load содержимого |
| `appointments.html` — календарь без библиотеки | Средняя | Использовать простой table-based календарь (no external deps) |
| Terminology замена "customer" → "patient" ломает JS-логику | Средняя | Только видимый текст; JS-переменные/API-ключи не менять |
| `knowledge.html` Services Catalog нужны новые API поля | Низкая | Backend уже возвращает `category` + `attributes` — использовать их |
