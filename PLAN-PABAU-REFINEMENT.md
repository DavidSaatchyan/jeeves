# Pabau Connector — Refinement Plan

## Цель
Доработать PabauConnector и смежные компоненты для production-ready работы: исправить найденные баги, добавить недостающие методы, улучшить обработку ошибок.

---

## Найденные проблемы

### 1. Webhook: `_verify()` не вызывает `adapter.verify_webhook_signature()`
**Файл:** `api/app/integrations/webhooks.py:30-36, 115-172`

`_process_webhook()` вызывает статическую `_verify(payload_bytes, signature, config)`, которая делает HMAC-SHA256 напрямую из `config["webhook_secret"]`. Адаптерный метод `adapter.verify_webhook_signature()` **никогда не вызывается**.

Для Cliniko это баг: если у тенанта есть `webhook_secret`, все Cliniko-вебхуки будут отвергнуты, т.к. Cliniko не подписывает запросы. Для Pabau работает только случайно (оба используют HMAC-SHA256).

**Исправление:** `_process_webhook()` должна вызывать `adapter.verify_webhook_signature(payload_bytes, signature)` вместо/в дополнение к `_verify()`. Либо убрать `_verify` и полностью делегировать проверку адаптеру.

### 2. `configure_crm` не сохраняет `shard`
**Файл:** `api/app/admin/pabau.py:47-60`

`CrmConfigUpdate` имеет поле `shard`, но `configure_crm` сохраняет только `api_key`, `company_id`, `webhook_secret`:
```python
tenant.crm_config = {
    "api_key": data.api_key,
    "company_id": data.company_id,
    "webhook_secret": data.webhook_secret,
}
```
`data.shard` игнорируется. Если tenant использует Cliniko с нестандартным shard, это не сработает.

**Исправление:** Добавить `"shard": data.shard` в сохраняемый dict.

### 3. `configure_crm` всегда сохраняет `crm_provider = "pabau"`, но есть поле
**Файл:** `api/app/admin/pabau.py:58`

После рефакторинга добавлено `data.crm_provider`, но для Cliniko настройки используется отдельная страница `admin/cliniko.py`, которая сохраняет `crm_provider = "cliniko"`. Pabau-страница тоже сохраняет своё значение. Это работает, но если в будущем появится generic CRM configure, нужно убедиться что провайдер передаётся.

### 4. `_maybe_crm_bridge()` молча глотает все исключения
**Файл:** `api/app/channels/whatsapp.py:71-86`

```python
try:
    patient = adapter.find_patient(phone=wa_id)
    if not patient:
        adapter.create_patient({...})
except Exception:
    pass
```

Любая ошибка (сеть, таймаут, 500) молча проглатывается. Пользователь не получает уведомления, что CRM-мост сломан. В логах тоже ничего нет.

**Исправление:** Логировать ошибку через `logger.warning()` или `logger.error()`.

### 5. `find_patient()` использует общий `search` вместо точных фильтров
**Файл:** `api/app/integrations/pabau.py:67-78`

```python
params = {}
if email:
    params["search"] = email
elif phone:
    params["search"] = phone
```

Pabau API может поддерживать раздельные фильтры `email=...` и `phone=...`. Сейчас если есть и email, и phone, выбирается только email. Нет возможности искать по обоим полям одновременно (для сверки).

**Исправление:** Узнать точный API Pabau для фильтрации пациентов. Если поддерживает — использовать `email` и `phone` отдельно. Хотя бы добавить TODO с документацией.

### 6. `search_available_slots()` возвращает `[]` — нет реальной интеграции
**Файл:** `api/app/integrations/pabau.py:143-144`

```python
def search_available_slots(self, doctor_id: str, date: str) -> list[dict[str, Any]]:
    return []
```

Слоты генерируются локально в `slot_manager.py` из расписания провайдера. Pabau API не используется для реальной проверки доступности. Это означает:
- Нет синхронизации с реальным расписанием Pabau
- Двойное бронирование возможно, если слот уже занят в Pabau
- После `book_appointment()` может быть 409 Conflict

**Возможные решения:**
- Узнать, есть ли в Pabau API эндпоинт для проверки доступности (GET availability/slots)
- Если нет — оставить, но добавить fallback-проверку при создании встречи (если Pabau вернул 409, вернуть клиенту SlotAlreadyBookedError)

### 7. Нет `get_practitioners()` / `get_providers()`
**Файл:** `api/app/integrations/pabau.py`

Для Cliniko есть `get_practitioners()` и `get_practitioner_by_id()`. Для Pabau — нет. 
В `slot_manager.py` провайдеры берутся из локальной таблицы `Provider`, а не из CRM. Если в Pabau добавили нового специалиста, он не появится в системе до ручного добавления.

**Исправление:** Добавить `get_practitioners()` → `GET /staff` или `GET /providers` (зависит от Pabau API).

### 8. `list_appointments()` возвращает raw dict без нормализации
**Файл:** `api/app/integrations/pabau.py:109-131`

Возвращает сырой ответ от Pabau API. Разные версии Pabau могут возвращать разную структуру (items, data, _embedded и т.д.). В `get_patient_appointments()` уже есть попытка нормализации:
```python
if isinstance(result, dict):
    return result.get("items", result.get("data", []))
```

Но `list_appointments()` не нормализует ответ.

**Исправление:** Добавить нормализацию в `list_appointments()` по тому же паттерну.

### 9. `_request()` не передаёт `**kwargs` в `httpx.request()` корректно при error handling
**Файл:** `api/app/integrations/pabau.py:39-57`

Если `_request()` вызывается с большим payload (например, `json={...}`), и происходит сетевой таймаут, `kwargs` может содержать уже прочитанные данные. При переповторе это не проблема (нет retry), но потенциально может вызвать утечку данных в логах.

**Исправление:** Не критично для MVP. Добавить TODO.

### 10. `from ...integrations.resolver import get_crm_adapter` — lazy import в 4 местах
**Файлы:**
- `api/app/core/booking/__init__.py:8` — module-level import (OK)
- `api/app/core/booking/slot_manager.py:104` — local import (lazy, OK)
- `api/app/channels/whatsapp.py:72` — local import (lazy, OK)
- `api/app/core/booking/__init__.py:24` — `from ...models import AppointmentCache` local import

Нет единообразия: `booking/__init__.py` делает module-level import для `get_crm_adapter`, a `slot_manager.py` и `whatsapp.py` — lazy local import. Не баг, но стоит унифицировать.

---

## План доработок

### Фаза 1: Критические баги (production safety)

| № | Задача | Файл(ы) | Риск |
|---|--------|---------|------|
| 1.1 | Webhook: делегировать verify адаптеру | `webhooks.py` | Без этого Cliniko webhooks не работают с настроенным secret |
| 1.2 | `configure_crm` сохранять `shard` | `admin/pabau.py` | Cliniko с нестандартным shard не настраивается |
| 1.3 | `_maybe_crm_bridge` логировать ошибки | `channels/whatsapp.py` | Тихие падения CRM-моста |

### Фаза 2: Функциональность (feature parity с Cliniko)

| № | Задача | Файл(ы) |
|---|--------|---------|
| 2.1 | Добавить `get_practitioners()` → `GET /staff` | `pabau.py` |
| 2.2 | Добавить `get_services()` / `get_appointment_types()` | `pabau.py` |
| 2.3 | Нормализовать `list_appointments()` ответ | `pabau.py` |

### Фаза 3: Улучшения (quality of life)

| № | Задача | Файл(ы) |
|---|--------|---------|
| 3.1 | Унифицировать импорты resolver | `booking/__init__.py`, `slot_manager.py`, `whatsapp.py` |
| 3.2 | Slot availability: проверить Pabau API эндпоинт | `pabau.py`, `slot_manager.py` |
| 3.3 | `find_patient()` — добавить поддержку обоих полей (email + phone) | `pabau.py` |
| 3.4 | AbstractCrmConnector: добавить `get_practitioners()` в базовый класс | `base.py` |

### Фаза 4: Тесты

| № | Задача | Файл(ы) |
|---|--------|---------|
| 4.1 | Добавить тесты для новых методов Pabau | `test_pabau_connector.py` |
| 4.2 | Обновить webhook тесты (verify делегирование) | `test_webhooks.py` |
| 4.3 | Добавить тест `configure_crm` сохранения shard | `test_admin_pabau.py` |

---

## Приоритеты реализации

```
Фаза 1 → Фаза 2 → Фаза 4 → Фаза 3
```

**Фаза 1** — блокирующая для production (Cliniko webhooks сломаны).
**Фаза 2** — feature parity между провайдерами.
**Фаза 4** — тесты для новых изменений.
**Фаза 3** — некритичные улучшения.

---

## Контекст

- Pabau API base: `https://api.pabau.com`
- Аутентификация: `X-API-Key` + `X-Company-Id`
- Method for update: `PATCH`, для cancel: `DELETE`
- Webhook signature: HMAC-SHA256 с `webhook_secret`
- Slot availability: не реализована (возвращает `[]`)
- Пациенты: создаются через `_maybe_crm_bridge` при первом сообщении в WhatsApp
