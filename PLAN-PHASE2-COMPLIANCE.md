# Phase 2: Compliance Layer — План реализации

> **Дата:** 2026-05-31
> **Базовый документ:** REBRAND-MEDICAL.md (Phase 2: Days 4-7)
> **Время:** ~4 дня

---

## 1. Цель

Создать compliance-слой для обработки медицинских данных пациентов в соответствии с **GDPR (EU)** и **HIPAA-ready (US)**. 
Обеспечить консент-менеджмент, минимизацию PHI, неизменяемый аудит и политики хранения данных.

---

## 2. Задачи

### 2.1. Модели данных — `models.py`

Добавить 6 новых моделей:

| Модель | Таблица | Назначение |
|--------|---------|------------|
| `Patient` | `patients` | Пациент (уже есть stub — доработать до полной модели) |
| `Appointment` | `appointments` | Запись на приём |
| `ConsentLog` | `consent_logs` | Журнал согласий (GDPR Art. 7) |
| `Provider` | `providers` | Врач/специалист |
| `CrmConnection` | `crm_connections` | Подключение к CRM |
| `AuditLog` | `audit_logs` | Расширенный аудит для compliance |

#### Patient (доработка существующего stub)

| Поле | Тип | Назначение |
|------|-----|------------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | |
| `external_id` | Text | CRM patient ID |
| `first_name` | Text | |
| `last_name` | Text | |
| `email` | Text | |
| `phone` | Text | |
| `date_of_birth` | DateTime | |
| `gender` | String(16) | |
| `consent_status` | String(16) | `pending / granted / revoked / expired` |
| `consent_timestamp` | DateTime | |
| `consent_channel` | String(32) | `whatsapp / widget / web / admin` |
| `gdpr_data_retention` | String(32) | Применённая политика хранения |
| `extra_data` | JSONB | CRM-specific fields |
| `created_at` | DateTime | |
| `updated_at` | DateTime | |

#### Appointment

| Поле | Тип | Назначение |
|------|-----|------------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | |
| `patient_id` | UUID FK → patients | |
| `external_id` | Text | CRM appointment ID |
| `provider_name` | Text | |
| `provider_specialty` | Text | |
| `department` | Text | |
| `start_time` | DateTime | |
| `end_time` | DateTime | |
| `status` | String(32) | `scheduled / confirmed / arrived / in_progress / completed / cancelled / no_show / rescheduled` |
| `reason` | Text | Причина визита |
| `notes` | Text | |
| `source` | String(32) | `whatsapp / widget / crm / web` |
| `slot_token` | String(64) | Оптимистичная блокировка слота |
| `reminder_sent_24h` | Boolean | |
| `reminder_sent_2h` | Boolean | |
| `consent_id` | UUID FK → consent_logs | |
| `created_at` | DateTime | |
| `updated_at` | DateTime | |

#### ConsentLog

| Поле | Тип | Назначение |
|------|-----|------------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | |
| `patient_id` | UUID FK → patients | |
| `type` | String(32) | `marketing / appointment / phi_whatsapp / data_processing` |
| `status` | String(16) | `granted / revoked / expired` |
| `channel` | String(32) | `whatsapp / widget / web / admin` |
| `consent_text` | Text | Точный текст согласия |
| `ip_address` | String(45) | |
| `user_agent` | Text | |
| `granted_at` | DateTime | |
| `revoked_at` | DateTime | |
| `expires_at` | DateTime | |

#### Provider

| Поле | Тип | Назначение |
|------|-----|------------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | |
| `external_id` | Text | CRM provider ID |
| `name` | Text | |
| `specialty` | Text | |
| `email` | Text | |
| `phone` | Text | |
| `schedule` | JSONB | Правила доступности |
| `created_at` | DateTime | |
| `updated_at` | DateTime | |

#### CrmConnection

| Поле | Тип | Назначение |
|------|-----|------------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | |
| `provider` | String(32) | `zoho / hubspot / salesforce / custom_api` |
| `config` | JSONB | Зашифрованные credentials, endpoint'ы, маппинги |
| `status` | String(16) | `connected / disconnected / error` |
| `last_sync_at` | DateTime | |
| `webhook_secret` | Text | |
| `created_at` | DateTime | |
| `updated_at` | DateTime | |

#### AuditLog

| Поле | Тип | Назначение |
|------|-----|------------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK → tenants | |
| `patient_id` | UUID FK → patients | |
| `actor_type` | String(16) | `patient / staff / system / whatsapp` |
| `actor_id` | Text | |
| `action` | String(64) | `message_sent / appointment_booked / consent_granted / phi_accessed / data_deleted` |
| `resource_type` | String(32) | |
| `resource_id` | Text | |
| `details` | JSONB | Не сырая PHI — только ссылки/токены |
| `ip_address` | String(45) | |
| `timestamp` | DateTime | |
| `retention_until` | DateTime | |

---

### 2.2. Модуль `core/compliance/`

Создать пакет из 4 модулей:

```
core/compliance/
├── __init__.py
├── consent.py        # ConsentManager — capture, renew, revoke
├── phi_minimization.py  # PHI stripping, tokenized link generation
├── audit.py          # AuditLogger — запись и query событий
└── retention.py      # RetentionPolicy — политики и чистка
```

#### `consent.py` — ConsentManager

```
ConsentManager
├── capture(patient_id, type, channel, text, ip) → ConsentLog
├── revoke(consent_id) → bool
├── renew(consent_id) → ConsentLog
├── is_valid(patient_id, type) → bool
├── get_active_consents(patient_id) → List[ConsentLog]
├── get_expiring_consents(before: datetime) → List[ConsentLog]
└── get_consent_history(patient_id, type) → List[ConsentLog]
```

Поведение:
- `capture` всегда создаёт новую запись (иммутабельный журнал)
- `revoke` устанавливает `status = revoked` и `revoked_at = now`
- `renew` создаёт новую запись с новым `expires_at`
- `is_valid` проверяет наличие `granted` + `expires_at > now`
- `get_expiring_consents` — для scheduled task по уведомлениям

#### `phi_minimization.py` — PHIMinimizer

```
PHIMinimizer
├── strip_phi(text) → str                    # Удалить PHI из текста
├── make_secure_link(resource_type, id) → str  # Создать tokenized ссылку
├── is_phi(text) → bool                      # Эвристика: содержит PHI?
└── tokenize(patient_id, resource) → Token    # Создать временный токен доступа
```

Правила:
- № телефона → `[PHONE]`
- Email → `[EMAIL]`
- Имя/фамилия → `[NAME]`
- Дата рождения → `[DOB]`
- Медицинский диагноз → `[DIAGNOSIS]`
- Адрес → `[ADDRESS]`

#### `audit.py` — AuditLogger

```
AuditLogger
├── log(actor_type, actor_id, action, resource_type, resource_id, details) → AuditLog
├── query(tenant_id, filters) → List[AuditLog]
├── get_patient_timeline(patient_id) → List[AuditLog]
└── export(tenant_id, date_range) → CSV/JSON
```

Интеграция:
- Вызывается из `timeline/recorder.py` для compliance-событий
- Используется в `admin/compliance.py` для дашборда

#### `retention.py` — RetentionPolicy

```
RetentionPolicy
├── get_policy(data_type) → timedelta          # Политика хранения для типа
├── apply_policy(patient) → None               # Установить retention_until
├── find_expired_records() → List[AuditLog]    # Для scheduled purge
├── anonymize_patient(patient) → bool          # Анонимизация вместо удаления
└── delete_expired(tenant_id) → int            # Scheduled task — физическое удаление
```

Default политики (из YAML config):
| Тип данных | Retention |
|-----------|-----------|
| `audit_log` | 3 года |
| `consent_log` | 6 лет (GDPR Art. 7) |
| `messages` | 2 года |
| `patient_records` | 10 лет (HIPAA) |
| `appointments` | 3 года |

---

### 2.3. Интеграция в существующие модули

#### `core/timeline/recorder.py`

Добавить вызов `AuditLogger.log()` для compliance-критических событий:
- Смена статуса согласия
- Доступ к PHI
- Экспорт данных
- Удаление данных

#### `channels/widget.py`

Добавить вызов `ConsentManager.capture()` при:
- Отправке формы с согласием на обработку данных
- Первом сообщении от нового пациента (implied consent)

#### `admin/compliance.py` — новый модуль

API endpoints:
```
GET  /admin/api/compliance/consents?patient_id=&type=&status=
POST /admin/api/compliance/consents/revoke
GET  /admin/api/compliance/audit?patient_id=&action=&from_date=&to_date=
GET  /admin/api/compliance/audit/export?from_date=&to_date=
GET  /admin/api/compliance/retention/settings
PUT  /admin/api/compliance/retention/settings
POST /admin/api/compliance/retention/purge
```

---

### 2.4. Alembic миграция

Создать новую миграцию (`phase2_add_compliance_models`):

1. **CREATE** таблицы: `patients` (если не существует), `appointments`, `consent_logs`, `providers`, `crm_connections`, `audit_logs`
2. **CREATE** индексы: все `tenant_id`, `patient_id`, `audit_logs.action`, `consent_logs.type + status`
3. **ALTER** `patients` — добавить поля если таблица уже создана в Phase 1

Команда:
```bash
cd api && python -m alembic revision --autogenerate -m "phase2_add_compliance_models"
```

---

### 2.5. Config — новые параметры

Добавить в `Settings` (config.py):

```python
# Compliance
compliance_gdpr_enabled: bool = True
compliance_hipaa_enabled: bool = False
compliance_audit_retention_days: int = 1095  # 3 years
compliance_consent_auto_renew_days: int = 365
compliance_data_residency: str = "auto"  # auto | eu | us
```

Добавить retention policies в `config.yaml`:

```yaml
compliance:
  retention:
    audit_log: 1095
    consent_log: 2190
    messages: 730
    patient_records: 3650
    appointments: 1095
  phi_patterns:
    - phone: '\+\d{7,15}'
    - email: '\S+@\S+'
    - name: '\b[A-Z][a-z]+\s[A-Z][a-z]+\b'
```

---

## 3. Порядок выполнения

| Шаг | Задача | Файлы | Проверка |
|-----|--------|-------|----------|
| 1 | Доработать `Patient` модель | `models.py` | `python -c "from app.models import Patient"` |
| 2 | Добавить `Appointment`, `ConsentLog`, `Provider` | `models.py` | |
| 3 | Добавить `CrmConnection`, `AuditLog` | `models.py` | |
| 4 | Обновить config | `config.py` | |
| 5 | Создать `core/compliance/consent.py` | `core/compliance/consent.py` | |
| 6 | Создать `core/compliance/phi_minimization.py` | `core/compliance/phi_minimization.py` | |
| 7 | Создать `core/compliance/audit.py` | `core/compliance/audit.py` | |
| 8 | Создать `core/compliance/retention.py` | `core/compliance/retention.py` | |
| 9 | Интегрировать `audit.py` в `timeline/recorder.py` | `core/timeline/recorder.py` | |
| 10 | Создать `admin/compliance.py` | `admin/compliance.py` | |
| 11 | Создать Alembic миграцию | `alembic/versions/` | `python -m alembic upgrade head` |
| 12 | Проверить imports | — | `python -c "from app.main import app"` |

---

## 4. Зависимости (Dependency Direction)

```
core/compliance → models, config, db           (ALLOWED)
core/compliance → core/timeline                 (ALLOWED — audit)
integrations/crm → core/compliance              (ALLOWED — PHI minimization)
channels/ → core/compliance                     (ALLOWED — consent)
admin/ → core/compliance                        (ALLOWED — compliance dashboard)

FORBIDDEN:
core/compliance → admin/, auth/, channels/      (NEVER — core не импортирует UI)
```

---

## 5. Критерии готовности (Definition of Done)

1. Все 6 моделей добавлены в `models.py` — `python -c "from app.models import ..."` проходит
2. Пакет `core/compliance/` создан — 4 модуля, каждый экспортирует свой класс
3. `ConsentManager` может: создать согласие, отозвать, проверить валидность
4. `PHIMinimizer` может: удалить PHI из текста, создать secure link
5. `AuditLogger` пишет события в БД, поддерживает query по tenant + фильтрам
6. `RetentionPolicy` определяет сроки хранения, находит истёкшие записи
7. `timeline/recorder.py` вызывает `AuditLogger.log()` для compliance-событий
8. `admin/compliance.py` API endpoints работают (consents, audit, retention)
9. Alembic миграция применяется без ошибок
10. `from app.main import app` — 0 ошибок импорта

---

## 6. Риски

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| Conflict полей `Customer` vs `Patient` | Средняя | Patient — новая таблица, Customer остаётся для legacy |
| PHI minimisation снижает качество логов | Низкая | Логи хранят tokenized ссылки, не сырые данные |
| Retention policy удаляет нужные данные | Низкая | Soft-delete + каскадная проверка перед hard-delete |
| GDPR/HIPAA требования меняются | Средняя | Политики в config.yaml, не хардкод |
| Производительность audit_logs | Средняя | Индексы на `tenant_id + timestamp`, партиционирование при необходимости |

---

## 7. Интеграция с Phase 3 (CRM)

`CrmConnection` закладывается сейчас, но наполняется в Phase 3:
- `integrations/crm/base.py` будет использовать `CrmConnection.config` для credentials
- `integrations/crm/zoho.py` будет создавать `Patient` при импорте из CRM
- `ConsentManager.capture()` будет вызываться при импорте consent из CRM

---

## 8. Связанные файлы

| Файл | Действие |
|------|----------|
| `api/app/models.py` | +6 моделей |
| `api/app/config.py` | +compliance параметры |
| `api/app/config.yaml` | +retention policies + PHI patterns |
| `api/app/core/compliance/__init__.py` | Создать |
| `api/app/core/compliance/consent.py` | Создать |
| `api/app/core/compliance/phi_minimization.py` | Создать |
| `api/app/core/compliance/audit.py` | Создать |
| `api/app/core/compliance/retention.py` | Создать |
| `api/app/core/timeline/recorder.py` | Интегрировать audit |
| `api/app/admin/compliance.py` | Создать |
| `api/app/admin/__init__.py` | Добавить импорт compliance |
| `api/app/templates/compliance.html` | Создать (заглушка) |
| `api/alembic/versions/*.py` | Новая миграция |
