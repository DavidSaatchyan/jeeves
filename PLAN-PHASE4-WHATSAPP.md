# Phase 4: WhatsApp Channel — Detailed Work Plan

> **Дата:** 2026-05-31
> **Базовый документ:** REBRAND-MEDICAL.md (Phase 4: Days 12–16)
> **Время:** ~4 дня

---

## 1. Цель

Активировать WhatsApp канал: переписать мёртвый код в `channels/whatsapp.py`, подключить через FastAPI роутер, добавить UI конфигурации, консент-менеджмент и интеграцию с CRM.

**Ключевой API:** WhatsApp Cloud API (Meta) — прямой вызов, без BSP.

---

## 2. Текущее состояние (AS-IS)

### Проблемы

| Проблема | Файл | Серьёзность |
|----------|------|-------------|
| Нет FastAPI роутера — эндпоинты не зарегистрированы | `channels/whatsapp.py` | **Critical** |
| `agent.run()` не импортирован — NameError | `channels/whatsapp.py:130` | **Critical** |
| `billing.enforce()` не импортирован — NameError | `channels/whatsapp.py:107` | **Critical** |
| `handle_webhook()` не импортируется в main.py | — | **Critical** |
| bare `except: pass` на строке 146 | `channels/whatsapp.py:146` | **Medium** |
| Webhook URL для Meta настраивается через админку — нет UI | `templates/channels.html` | **Medium** |
| `config.yaml` не включает whatsapp | `config.yaml` | **Low** |
| WhatsApp таб в админке — disabled "Soon" | `templates/channels.html:14-18` | **Medium** |

### Что уже работает

- `channels/registry.py` поддерживает `"whatsapp"` в `SUPPORTED_CHANNELS`
- `ChannelConfig` модель поддерживает `channel_type == "whatsapp"`
- `ChatLog`, `Conversation`, `Message`, `Patient` — уже имеют WhatsApp-поля
- `ConsentLog` имеет `type = "phi_whatsapp"` и `channel = "whatsapp"`
- `send_message()` — рабочий (использует `httpx.AsyncClient`)
- `verify_webhook()` — рабочий (Meta challenge)
- `validate_config()` — рабочий (проверяет phone_number_id + access_token)

---

## 3. Архитектура (TO-BE)

```
channels/
├── __init__.py               # (пусто)
├── registry.py               # ✅ существует — SUPPORTED_CHANNELS + lookup cache
├── widget.py                 # ✅ существует — эталонный канал
└── whatsapp.py               # 🔄 ПЕРЕПИСАТЬ — добавить APIRouter, исправить импорты

core/
├── ai/
│   └── generator.py → simple_llm_response()   # ✅ используется widget_channel
└── compliance/
    ├── consent.py → ConsentManager              # ✅ используется widget_channel
    └── phi_minimization.py → mask_phi()        # ✅ используется CRM webhooks

integrations/crm/
└── webhooks.py               # 🔄 добавить WhatsApp → CRM Webhook Bridge

config.yaml                    # 🔄 добавить whatsapp в allowed_channels
templates/channels.html        # 🔄 заменить "Soon" на форму конфигурации
admin/pages.py                 # ✅ channels_page уже существует
rate_limit.py                  # ✅ _LIMITS уже содержит "chat", "widget"
```

### Dependency Direction

```
channels/whatsapp.py → core/ai, core/compliance/consent, shared/inbox_writer  (ALLOWED)
channels/whatsapp.py → integrations/crm  (ALLOWED — для bridge webhook)
channels/whatsapp.py → models, db, config, rate_limit, moderation  (ALLOWED)

FORBIDDEN:
channels/whatsapp.py → admin/, auth/  (NEVER)
core/ → channels/whatsapp.py  (NEVER)
```

### Поток сообщений

```
Meta Cloud API
     │
     │ POST /webhook (inbound message)
     ▼
channels/whatsapp.py
  └─ verify_webhook() ← Meta GET challenge
  └─ handle_webhook()
       ├─ _resolve_tenant() → определяет tenant через business_phone
       ├─ ConsentManager.check() / capture()
       ├─ moderate() ← проверка контента
       ├─ check_rate_limit() ← анти-флуд
       ├─ add_message() / get_or_create_conversation()
       ├─ simple_llm_response() ← AI ответ
       ├─ send_message() ← отправка ответа
       └─ CRM bridge → _upsert_patient() (опционально)
```

---

## 4. Задачи

### 4.1. Переписать `channels/whatsapp.py` — добавить FastAPI роутер

Замена текущего набора сырых функций на полноценный `APIRouter` по образцу `widget.py`.

**Требования:**

```python
router = APIRouter(prefix="/channels/whatsapp", tags=["whatsapp"])
```

**Эндпоинты:**

| Метод | Путь | Назначение |
|-------|------|------------|
| `GET` | `/channels/whatsapp/webhook` | Meta verification challenge — `verify_webhook()` |
| `POST` | `/channels/whatsapp/webhook` | Приём входящих сообщений |

**Логика POST /webhook:**
1. Распарсить payload Meta Cloud API (entry → changes → value → messages)
2. `_resolve_tenant(db, wa_id)` — найти tenant по business_phone
3. `check_rate_limit("whatsapp", wa_id)` — анти-флуд (20/мин)
4. `moderate(text)` — проверка на запрещённый контент
5. `ConsentManager.check()` — проверить согласие на WhatsApp
6. `get_or_create_conversation(db, tenant.id, wa_id, channel="whatsapp")`
7. `add_message(db, conv, "incoming", text, sender_type="customer")`
8. `simple_llm_response(tenant.id, text, conversation_history=history)` — AI ответ
9. `add_message(db, conv, "outgoing", response, sender_type="bot")`
10. `send_message(phone_number_id, access_token, wa_id, response)` — отправка
11. `ChatLog` — запись лога
12. `db.commit()`

**Импорты (исправленные):**
```python
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import ChannelConfig, ChatLog, Tenant
from ..shared.inbox_writer import add_message, get_or_create_conversation
from ..core.ai import simple_llm_response
from ..core.compliance.consent import ConsentManager
from ..rate_limit import check_rate_limit
from ..moderation import moderate
```

**Удалить:**
- `agent.run()` — заменить на `simple_llm_response()`
- `billing.enforce()` — удалить (billing removed в Phase 1)
- `SessionLocal()` — заменить на `Depends(get_db)`

**Проверка:** `python -c "from channels.whatsapp import router"` проходит.

---

### 4.2. Подключить WhatsApp роутер в `main.py`

```python
from .channels import whatsapp as whatsapp_channel
app.include_router(whatsapp_channel.router)
```

**Проверка:** `python -c "from app.main import app"` проходит.

---

### 4.3. Добавить WhatsApp rate limit в `rate_limit.py`

```python
_LIMITS = {
    "login": (5, 60),
    "register": (3, 3600),
    "chat": (20, 60),
    "widget": (20, 60),
    "whatsapp": (30, 60),  # 30 messages per minute per WA ID
}
```

---

### 4.4. Обновить `config.yaml` — добавить WhatsApp в allowed_channels

```yaml
policies:
  communication:
    allowed_channels: [email, widget, whatsapp]
```

---

### 4.5. Обновить `templates/channels.html` — форма конфигурации WhatsApp

Убрать disabled-блокировку и "Soon". Добавить:

**Форма конфигурации:**
- `Phone Number ID` — text input
- `Access Token` — password input
- `Verify Token` — password input (для Meta webhook verification)
- `Business Phone` — text input (для tenant resolution)

**Webhook URL display:**
- Показать URL: `{public_base_url}/channels/whatsapp/webhook`
- Кнопка "Copy"

**Setup instructions:**
1. Go to Meta Developer Portal → WhatsApp → Configuration
2. Set the webhook URL to the URL shown below
3. Set the verify token to the one configured above
4. Subscribe to `messages` webhook field
5. Generate a permanent access token

**Actions:**
- "Save Configuration" — сохранить в `ChannelConfig`
- "Test Connection" — отправить тестовое сообщение себе
- "Disconnect" — удалить конфигурацию

**Проверка:** Страница отображается без "Soon", форма конфигурации активна.

---

### 4.6. Добавить WhatsApp → CRM Bridge

При получении WhatsApp сообщения, если у tenant-а есть активный CRM connector (Zoho), опционально создать/обновить пациента:

```python
def _maybe_crm_bridge(db: Session, tenant_id, wa_id: str, text: str, contact_name: str | None) -> None:
    """Create/update patient in CRM from WhatsApp contact."""
    from ..integrations.crm import get_crm_adapter
    from ..integrations.credentials import get_credentials
    try:
        config = get_credentials(tenant_id, "zoho", db)
        adapter = get_crm_adapter("zoho", config)
        patient = adapter.find_patient(phone=wa_id)
        if not patient:
            adapter.create_patient({
                "first_name": (contact_name or "").split()[0] if contact_name else "WhatsApp",
                "last_name": " ".join((contact_name or "").split()[1:]) if contact_name and len(contact_name.split()) > 1 else "User",
                "phone": wa_id,
            })
    except Exception:
        pass  # CRM is optional — don't break the message flow
```

---

### 4.7. Добавить WhatsApp consent enforcement

В `handle_webhook()`, перед обработкой сообщения:

```python
if not ConsentManager.check(db, tenant.id, wa_id, channel="whatsapp"):
    await send_message(phone_number_id, access_token, wa_id,
        "You haven't consented to receive messages. Reply 'YES' to opt in.")
    return {"ok": True, "consent_required": True}
```

Также обработать входящее "YES"/"OPT-IN" как capture consent:
```python
if text.strip().upper() in ("YES", "OPT-IN", "START", "CONSENT"):
    ConsentManager.capture(
        db=db,
        patient_id=None,
        consent_type="phi_whatsapp",
        channel="whatsapp",
        consent_text=f"Opt-in via WhatsApp message: {text[:100]}",
        tenant_id=tenant.id,
        ip_address="whatsapp",
    )
    await send_message(phone_number_id, access_token, wa_id,
        "Thank you! You're now opted in to receive messages.")
    return {"ok": True}
```

---

### 4.8. Обновить `channels/registry.py` — починить lookup cache

Текущий кеш использует `phone_number_id`, но `_resolve_tenant()` в WhatsApp сравнивает `business_phone`. Привести к единому ключу.

Исправить `build()`:
```python
for cfg in configs:
    if cfg.channel_type == "whatsapp":
        phone = cfg.config.get("business_phone", "")
        if phone:
            self._phone_to_tenant[phone] = cfg.tenant_id
```

---

### 4.9. Alembic миграция (если нужно)

**Проверить модель `ChannelConfig`:**
| Поле | Статус | Назначение |
|------|--------|------------|
| `id` | ✅ | UUID PK |
| `tenant_id` | ✅ | FK → tenants, indexed |
| `channel_type` | ✅ | "web_widget" / "whatsapp" |
| `config` (JSONB) | ✅ | credentials + настройки |
| `status` | ✅ | "active" / "inactive" |
| `last_error` | ✅ | текст ошибки |
| `created_at` | ✅ | |
| `updated_at` | ✅ | |

Миграция не требуется.

---

### 4.10. Обновить `core/communications/delivery.py`

Добавить WhatsApp как канал доставки в allowed_channels (уже есть в config.yaml).

---

## 5. Порядок выполнения

| Шаг | Задача | Файлы | Проверка |
|-----|--------|-------|----------|
| 1 | Переписать `whatsapp.py` — APIRouter + исправленные импорты | `channels/whatsapp.py` | `python -c "from channels.whatsapp import router"` |
| 2 | Подключить роутер в `main.py` | `main.py` | `python -c "from app.main import app"` |
| 3 | Добавить rate limit для WhatsApp | `rate_limit.py` | `check_rate_limit("whatsapp", "test")` returns bool |
| 4 | Обновить `config.yaml` | `config.yaml` | whatsapp в allowed_channels |
| 5 | Обновить `templates/channels.html` | `templates/channels.html` | Форма конфигурации активна |
| 6 | WhatsApp → CRM Bridge | `channels/whatsapp.py` | Вызов CRM при новом контакте |
| 7 | Consent enforcement | `channels/whatsapp.py` | Opt-in/opt-out обработка |
| 8 | Починить lookup cache | `channels/registry.py` | Единый ключ business_phone |
| 9 | Финальная проверка | — | `python -c "from app.main import app"` |
| 10 | Smoke test: отправить сообщение через API | — | POST /channels/whatsapp/webhook returns 200 |

---

## 6. Критерии готовности (Definition of Done)

1. `channels/whatsapp.py` содержит `APIRouter` с эндпоинтами `GET/POST /channels/whatsapp/webhook`
2. `main.py` импортирует и включает `whatsapp_channel.router`
3. Входящее WhatsApp сообщение: верификация → tenant resolution → rate limit → moderation → consent → AI → reply → log
4. Ответ отправляется обратно через WhatsApp Cloud API (`send_message()`)
5. `resolve_tenant()` использует `business_phone` (единый ключ с lookup cache)
6. `rate_limit.py` содержит `_LIMITS["whatsapp"]`
7. `config.yaml` содержит `whatsapp` в `allowed_channels`
8. `templates/channels.html` показывает активную форму для WhatsApp (не "Soon")
9. WhatsApp → CRM bridge работает (опционально, не блокирует сообщение)
10. Consent enforcement: opt-in через "YES"/"OPT-IN", блокировка без consent
11. `from app.main import app` — 0 ошибок импорта
12. Нет ссылок на `agent.run()`, `billing.enforce()`, `SessionLocal()` в whatasapp.py
13. Нет bare `except: pass`

---

## 7. Структура файлов после Phase 4

```
api/app/
├── channels/
│   ├── __init__.py
│   ├── registry.py           # ✅ SUPPORTED_CHANNELS + cache
│   ├── widget.py              # ✅ эталонный канал
│   └── whatsapp.py            # 🔄 APIRouter + Webhook + CRM Bridge
├── core/
│   ├── ai/generator.py        # ✅ simple_llm_response()
│   └── compliance/consent.py  # ✅ ConsentManager
├── integrations/crm/
│   └── webhooks.py            # ✅ CRM webhook bridge
├── admin/pages.py             # ✅ channels_page()
├── templates/channels.html    # 🔄 WhatsApp config form
├── rate_limit.py              # 🔄 _LIMITS["whatsapp"]
├── config.yaml                # 🔄 allowed_channels: +whatsapp
└── main.py                    # 🔄 +whatsapp_channel.router
```

---

## 8. Риски

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| Meta меняет формат webhook payload | Низкая | Версионировать API (`v17.0` → `v22.0`) |
| Access Token expires (24h для temporary) | Высокая | В UI require permanent token; предупреждение |
| Rate limits Meta (250 msg/sec per number) | Средняя | Наша rate limit — 30/мин; retry with backoff |
| Consent not given → message not delivered | Средняя | Отправить opt-in запрос; не блокировать полностью |
| CRM bridge failure блокирует сообщение | Средняя | `try/except` — CRM bridge опционален |
| phone_number_id vs business_phone путаница | Средняя | Единый ключ business_phone в registry + resolve |

---

## 9. Интеграция с Phase 3 (CRM)

Phase 4 использует CRM слой из Phase 3:
- WhatsApp contact → `CrmConnection` lookup → создание Contact в Zoho
- WhatsApp appointment booking → создание Appointment в Zoho
- CRM patient lookup → персонализация WhatsApp сообщения

---

## 10. Связанные файлы

| Файл | Действие |
|------|----------|
| `channels/whatsapp.py` | Переписать — APIRouter + исправленные импорты |
| `main.py` | Добавить `include_router(whatsapp_channel.router)` |
| `rate_limit.py` | Добавить `_LIMITS["whatsapp"]` |
| `config.yaml` | Добавить `whatsapp` в `allowed_channels` |
| `templates/channels.html` | Заменить "Soon" на форму конфигурации |
| `channels/registry.py` | Исправить ключ кеша на `business_phone` |
