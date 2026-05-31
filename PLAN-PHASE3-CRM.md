# Phase 3: CRM Integration — Detailed Work Plan

> **Дата:** 2026-05-31
> **Базовый документ:** REBRAND-MEDICAL.md (Phase 3: Days 8–12)
> **Время:** ~5 дней

---

## 1. Цель

Создать универсальный CRM connector framework для интеграции Jeeves с популярными клиническими CRM. Обеспечить двунаправленную синхронизацию пациентов, записей на приём и событий. 

**Ключевые CRM:** Zoho (P0, BAA ✓), HubSpot (P1, no PHI), Salesforce Health Cloud (P1, BAA ✓), Custom API (P0).

---

## 2. Архитектура

```
integrations/crm/
├── __init__.py          # Экспорт фабрики get_crm_adapter()
├── base.py              # AbstractCrmConnector — интерфейс всех адаптеров
├── zoho.py              # Zoho CRM adapter (BAA-compatible, PHI ✓)
├── hubspot.py           # HubSpot adapter (non-PHI marketing only)
├── salesforce.py        # Salesforce Health Cloud adapter (enterprise, BAA ✓)
├── custom_api.py        # Generic REST adapter for custom CRMs
└── webhooks.py          # CRM webhook receiver (rewrite of old webhooks.py)

models.py
  ├── CrmConnection      # Хранит config/credentials (уже создана в Phase 2)
  └── Patient.external_id # CRM patient ID (уже добавлена в Phase 2)

core/compliance/
  └── phi_minimization.py # Вызывается при импорте данных из CRM

admin/integrations.py    # CRUD для CrmConnection + тест коннектора
templates/connections.html # UI для настройки CRM (отредактировать)

alembic/versions/        # Новая миграция — изменения в CrmConnection
```

### Dependency Direction

```
integrations/crm/ → models, config, db, core/compliance  (ALLOWED)
integrations/crm/ → integrations/credentials              (ALLOWED)
admin/ → integrations/crm/                                (ALLOWED — API endpoints)

FORBIDDEN:
integrations/crm/ → admin/, auth/, channels/              (NEVER)
core/ → integrations/crm/                                 (NEVER — core не импортирует драйверы)
```

---

## 3. Задачи

### 3.1. Создать `integrations/crm/base.py` — AbstractCrmConnector

Абстрактный базовый класс, который определяет контракт для всех CRM адаптеров.

```python
class AbstractCrmConnector(ABC):
    provider: str  # "zoho" | "hubspot" | "salesforce" | "custom_api"

    @abstractmethod
    def __init__(self, config: dict): ...

    # ── Patients ──
    @abstractmethod
    def get_patient(self, patient_id: str) -> dict | None: ...
    @abstractmethod
    def find_patient(self, email: str | None = None, phone: str | None = None) -> dict | None: ...
    @abstractmethod
    def create_patient(self, data: dict) -> dict: ...
    @abstractmethod
    def update_patient(self, patient_id: str, data: dict) -> dict: ...

    # ── Appointments ──
    @abstractmethod
    def create_appointment(self, patient_id: str, data: dict) -> dict: ...
    @abstractmethod
    def update_appointment(self, appt_id: str, data: dict) -> dict: ...
    @abstractmethod
    def cancel_appointment(self, appt_id: str) -> bool: ...
    @abstractmethod
    def get_patient_appointments(self, patient_id: str) -> list[dict]: ...

    # ── Slots / Scheduling ──
    @abstractmethod
    def search_available_slots(self, doctor_id: str, date: str) -> list[dict]: ...

    # ── Webhooks ──
    @abstractmethod
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool: ...
    @abstractmethod
    def parse_webhook_event(self, payload: dict) -> dict: ...
```

Также добавить фабрику `get_crm_adapter(provider: str, config: dict) -> AbstractCrmConnector` и registry адаптеров.

**Проверка:** `python -c "from integrations.crm.base import AbstractCrmConnector"` проходит.

---

### 3.2. Создать `integrations/crm/zoho.py` — ZohoCRMAdapter

Первый и приоритетный адаптер (Zoho CRM — BAA доступен, PHI разрешён).

**Требуется:**
- OAuth 2.0 client credentials flow (Zoho Accounts API)
- Zoho CRM API v7 — модули: `Contacts` (пациенты), `Appointments` (custom module или `Events`)
- Поддержка кастомных полей (Zoho позволяет маппинг через конфиг)
- PHI-safe: все запросы через TLS 1.2+, токены хранятся зашифрованными в `CrmConnection.config`

**Методы:**
- `_refresh_token()` — автоматическое обновление access_token по refresh_token
- `_api_request(method, path, data)` — обёртка для Zoho REST API
- `get_patient(patient_id)` → GET `/crm/v7/Contacts/{patient_id}`
- `find_patient(email, phone)` → GET `/crm/v7/Contacts/search?email=...` или `?phone=...`
- `create_patient(data)` → POST `/crm/v7/Contacts`
- `update_patient(patient_id, data)` → PUT `/crm/v7/Contacts/{patient_id}`
- `create_appointment(patient_id, data)` → POST `/crm/v7/Appointments__s` (custom module)
- `update_appointment(appt_id, data)` → PUT `/crm/v7/Appointments__s/{appt_id}`
- `cancel_appointment(appt_id)` → PUT со статусом "Cancelled"
- `get_patient_appointments(patient_id)` → GET `/crm/v7/Appointments__s/search?Patient_ID={id}`
- `search_available_slots(doctor_id, date)` → GET `/crm/v7/Doctors__s/{doctor_id}/Slots__s`
- `verify_webhook_signature(payload, signature)` — Zoho webhook HMAC verification

**OAuth Config (tenant-level, хранится в `CrmConnection.config`):**
```yaml
client_id: str
client_secret: str       # encrypted
refresh_token: str       # encrypted
accounts_domain: str     # accounts.zoho.com | accounts.zoho.eu | ...
api_domain: str          # www.zohoapis.com | www.zohoapis.eu | ...
```

**Проверка:** `python -c "from integrations.crm.zoho import ZohoCRMAdapter"` проходит.

---

### 3.3. Создать `integrations/crm/hubspot.py` — HubSpotAdapter

Второй адаптер — для non-PHI маркетинговых операций (Email-маркетинг, лид-генерация).

**Ограничения:** Не используется для PHI. Только для consented marketing communications.

**Требуется:**
- OAuth 2.0 (HubSpot App)
- Private App token (альтернатива)
- HubSpot CRM API — модули: `Contacts`, `Deals`, `Engagements`

**Проверка:** `python -c "from integrations.crm.hubspot import HubSpotAdapter"` проходит.

---

### 3.4. Создать `integrations/crm/salesforce.py` — SalesforceAdapter (заглушка)

Enterprise-адаптер для Salesforce Health Cloud.

**Phase 3 — только заглушка** с документированным интерфейсом. Полная реализация в Phase 5+.

**Ожидаемый API:**
- OAuth 2.0 JWT Bearer Token (Server-to-Server)
- Salesforce REST API — `/services/data/v58.0/`
- Модули: `Patient__c`, `Appointment__c`, `Provider__c`, `Slot__c`

**Проверка:** `python -c "from integrations.crm.salesforce import SalesforceAdapter"` проходит (если файл существует).

---

### 3.5. Создать `integrations/crm/custom_api.py` — CustomApiAdapter

Generic REST adapter для клиник с собственными CRM.

**Работает по конфигу:**
```yaml
base_url: str
auth_type: bearer | basic | api_key | custom
auth_credentials: dict    # encrypted
endpoint_mapping: dict    # path for each method
headers: dict
```

Читает маппинг endpoint'ов из `CrmConnection.config` и выполняет HTTP-запросы.

**Проверка:** `python -c "from integrations.crm.custom_api import CustomApiAdapter"` проходит.

---

### 3.6. Создать `integrations/crm/__init__.py`

Фабрика + registry:

```python
_registry: dict[str, type[AbstractCrmConnector]] = {}

def register_crm_provider(provider: str, cls: type[AbstractCrmConnector]) -> None:
    _registry[provider] = cls

def get_crm_adapter(provider: str, config: dict) -> AbstractCrmConnector:
    cls = _registry.get(provider)
    if cls is None:
        raise ConnectorError(f"Unknown CRM provider: {provider}")
    return cls(config)

def list_crm_providers() -> list[str]:
    return list(_registry.keys())
```

Авторегистрация при импорте модулей.

**Проверка:** `python -c "from integrations.crm import get_crm_adapter, list_crm_providers"` проходит.

---

### 3.7. Создать `integrations/crm/webhooks.py`

Webhook receiver для входящих событий от CRM (создание/обновление пациента, appointment created и т.д.).

**Router:** `APIRouter(prefix="/integrations/webhooks/{provider}", tags=["webhooks"])`

**Endpoints:**
```
POST /integrations/webhooks/zoho    — Zoho webhooks
POST /integrations/webhooks/hubspot — HubSpot webhooks
POST /integrations/webhooks/custom  — Custom API webhooks
```

**Логика:**
1. Проверить `X-Webhook-Signature` (HMAC/токен из `CrmConnection.webhook_secret`)
2. Распарсить событие через адаптер (`parse_webhook_event`)
3. Создать/обновить `Patient` в локальной БД
4. Создать/обновить `Appointment` в локальной БД
5. Записать `AuditLog` (compliance)
6. Вернуть 200 OK

**Интеграция в `main.py`:** `app.include_router(crm_webhooks.router)`

**Проверка:** `python -c "from integrations.crm.webhooks import router"` проходит.

---

### 3.8. Обновить `admin/integrations.py` — CRM API endpoints

Добавить/обновить CRUD для `CrmConnection`:

```
GET    /api/crm/connections                     — список подключений
POST   /api/crm/connections                     — создать подключение
PUT    /api/crm/connections/{id}                — обновить конфиг
DELETE /api/crm/connections/{id}                — удалить подключение
POST   /api/crm/connections/{id}/test           — тест подключения
GET    /api/crm/connections/{id}/sync           — ручная синхронизация
```

**Модель ответа:**
```json
{
  "id": "uuid",
  "provider": "zoho",
  "status": "connected | disconnected | error",
  "config_mask": {"client_id": "••••", "api_domain": "www.zohoapis.com"},
  "last_sync_at": "2026-06-01T12:00:00Z"
}
```

**Проверка:** `GET /admin/api/crm/connections` возвращает 200.

---

### 3.9. Обновить `admin/integrations.py` — добавить CRM в существующие интеграции

Обновить `_CONNECTOR_FIELDS` в `admin/integrations.py`:

```python
_CONNECTOR_FIELDS: dict[str, list[str]] = {
    "zoho": ["client_id", "client_secret", "refresh_token", "accounts_domain", "api_domain"],
    "hubspot": ["access_token", "portal_id"],
    "salesforce": ["client_id", "client_secret", "username", "password", "security_token"],
    "custom_api": ["base_url", "auth_type", "endpoint_mapping"],
}
```

Обновить `_WEBHOOK_EVENTS`:
```python
_WEBHOOK_EVENTS: dict[str, list[str]] = {
    "zoho": ["Contacts.create", "Contacts.edit", "Appointments__s.create", "Appointments__s.edit"],
    "hubspot": ["contact.creation", "contact.propertyChange"],
}
```

---

### 3.10. Обновить `templates/connections.html` — CRM UI

- Заменить Shopify-специфичные поля на CRM-конфигурацию
- Добавить выпадающий список провайдеров: Zoho, HubSpot, Salesforce, Custom API
- Показать соответствующие поля конфигурации при выборе провайдера
- Кнопка "Test Connection" + индикатор статуса
- Webhook URL для каждого подключённого провайдера
- Кнопка "Sync Now" для ручной синхронизации

---

### 3.11. Обновить `integrations/credentials.py`

Добавить CRM провайдеров в `_PROVIDERS`:

```python
_PROVIDERS: frozenset[str] = frozenset({"zoho", "hubspot", "salesforce", "custom_api"})
```

---

### 3.12. Alembic миграция

**Изменения в `crm_connections` (`models.py`):**

Убедиться, что `CrmConnection` содержит все нужные поля (должны быть созданы в Phase 2):

| Поле | Статус |
|------|--------|
| `id` | ✅ |
| `tenant_id` | ✅ |
| `provider` | ✅ |
| `config` (JSONB, encrypted credentials) | ✅ |
| `status` | ✅ |
| `last_sync_at` | ✅ |
| `webhook_secret` | ✅ |
| `created_at` | ✅ |
| `updated_at` | ✅ |

**Если полей не хватает** — создать новую миграцию с ALTER TABLE.

---

### 3.13. Интеграция PHI-minimization

При импорте данных из CRM (через webhooks или sync) вызывать `core/compliance/phi_minimization.py`:

```python
from core.compliance.phi_minimization import PHIMinimizer

class ZohoCRMAdapter(AbstractCrmConnector):
    def get_patient(self, patient_id: str) -> dict | None:
        data = self._api_request("GET", f"/crm/v7/Contacts/{patient_id}")
        if data and self._phi_safe:
            data = PHIMinimizer.strip_phi(data)  # маскировать PHI для non-PHI storage
        return data
```

**Важно:** `phi_safe` флаг в конфиге — `True` для Zoho/Salesforce (BAA signed), `False` для HubSpot (PHI не передаётся).

---

## 4. Порядок выполнения

| Шаг | Задача | Файлы | Проверка |
|-----|--------|-------|----------|
| 1 | Создать `base.py` — `AbstractCrmConnector` + фабрика | `integrations/crm/base.py`, `integrations/crm/__init__.py` | `python -c "from integrations.crm.base import AbstractCrmConnector"` |
| 2 | Создать `zoho.py` — ZohoCRMAdapter | `integrations/crm/zoho.py` | `python -c "from integrations.crm.zoho import ZohoCRMAdapter"` |
| 3 | Создать `hubspot.py` — HubSpotAdapter (заглушка) | `integrations/crm/hubspot.py` | Импорт проходит |
| 4 | Создать `salesforce.py` — заглушка | `integrations/crm/salesforce.py` | Импорт проходит |
| 5 | Создать `custom_api.py` — CustomApiAdapter | `integrations/crm/custom_api.py` | Импорт проходит |
| 6 | Обновить `integrations/crm/__init__.py` — registry + фабрика | `integrations/crm/__init__.py` | `get_crm_adapter()`, `list_crm_providers()` работают |
| 7 | Создать `integrations/crm/webhooks.py` — webhook receiver | `integrations/crm/webhooks.py` | `POST /integrations/webhooks/zoho` returns 200 |
| 8 | Обновить `admin/integrations.py` — CRM API endpoints | `admin/integrations.py` | `GET /admin/api/crm/connections` returns 200 |
| 9 | Обновить `templates/connections.html` — CRM UI | `templates/connections.html` | UI показывает CRM провайдеров |
| 10 | Обновить `integrations/credentials.py` — CRM providers | `integrations/credentials.py` | `_PROVIDERS` содержит CRM |
| 11 | Обновить `main.py` — include CRM webhooks router | `main.py` | Импорт проходит |
| 12 | Alembic миграция (если нужно) | `alembic/versions/*.py` | `python -m alembic upgrade head` |
| 13 | Интеграция PHI-minimization | `integrations/crm/zoho.py` | PHI маскируется для non-PHI провайдеров |
| 14 | Финальная проверка | — | `python -c "from app.main import app"` |

---

## 5. Критерии готовности (Definition of Done)

1. `AbstractCrmConnector` определён — все 13 методов с `@abstractmethod`
2. Все 4 адаптера созданы (Zoho — полный, HubSpot — рабочий non-PHI, Salesforce — заглушка, CustomAPI — generic)
3. `get_crm_adapter(provider, config)` возвращает корректный инстанс
4. `list_crm_providers()` возвращает `["zoho", "hubspot", "salesforce", "custom_api"]`
5. ZohoCRMAdapter может: получить пациента, создать запись, найти по email/phone
6. Webhook receiver принимает и обрабатывает CRM события
7. `admin/integrations.py` имеет CRUD для `CrmConnection` + тест коннектора
8. `connections.html` показывает UI для настройки CRM
9. `integrations/credentials.py` содержит все 4 CRM провайдера
10. `from app.main import app` — 0 ошибок импорта
11. PHI минимизация вызывается при импорте из non-BAA провайдеров

---

## 6. Структура файлов

```
api/app/integrations/crm/
├── __init__.py            # Фабрика + registry
├── base.py                # AbstractCrmConnector
├── zoho.py                # Zoho CRM adapter
├── hubspot.py             # HubSpot adapter
├── salesforce.py          # Salesforce adapter (stub)
├── custom_api.py          # Custom API adapter
├── webhooks.py            # CRM webhook receiver
├── exceptions.py          # CrmConnectionError, CrmAuthError, CrmNotFoundError
└── models.py              # Pydantic модели для ответов CRM (опционально)

api/app/admin/integrations.py  # +CRM CRUD endpoints
api/app/templates/connections.html  # +CRM UI
```

---

## 7. Риски

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| Zoho OAuth token expires mid-session | Высокая | Автоматический refresh_token в `_api_request()` |
| Rate limits Zoho API (250 req/min) | Средняя | Retry with backoff + очередь запросов |
| Разные версии API у инстансов Zoho (EU, US, AU, IN) | Средняя | Конфигурируемый `api_domain` в `CrmConnection.config` |
| HubSpot PHI restrictions (нет BAA без Enterprise) | Средняя | Адаптер возвращает ошибку при попытке записи PHI |
| Custom CRM не имеет REST API | Низкая | Клиники с такими CRM не target — CustomAPI рассчитан на REST-совместимые |
| Webhook signature verification differs per CRM | Средняя | Каждый адаптер реализует свой `verify_webhook_signature()` |

---

## 8. Интеграция с Phase 4 (WhatsApp)

Phase 3 закладывает CRM слой, который будет использован в Phase 4:
- WhatsApp webhooks → CRM webhooks → создание пациента в CRM
- WhatsApp appointment booking → CRM appointment creation
- CRM patient lookup → WhatsApp message personalisation

---

## 9. Связанные файлы

| Файл | Действие |
|------|----------|
| `integrations/crm/base.py` | Создать |
| `integrations/crm/__init__.py` | Создать |
| `integrations/crm/zoho.py` | Создать |
| `integrations/crm/hubspot.py` | Создать |
| `integrations/crm/salesforce.py` | Создать (заглушка) |
| `integrations/crm/custom_api.py` | Создать |
| `integrations/crm/webhooks.py` | Создать |
| `integrations/crm/exceptions.py` | Создать |
| `integrations/credentials.py` | Обновить `_PROVIDERS` |
| `admin/integrations.py` | Добавить CRM CRUD |
| `templates/connections.html` | Обновить UI |
| `main.py` | Добавить include CRM webhooks |
| `alembic/versions/*.py` | Новая миграция (если нужно) |
