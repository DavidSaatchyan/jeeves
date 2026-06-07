# HMS Sync: Current State & Design Analysis

## 0. Self-Critique (v2 corrections)

Первая версия этого документа содержала ошибки и перегибы. Вот что исправлено:

| Ошибка в v1 | Исправление |
|-------------|-------------|
| Утверждение, что Cliniko поддерживает webhooks | **Неподтверждено.** Официальная API документация (`docs.api.cliniko.com`) и Help Center не упоминают webhooks. Код `verify_webhook_signature` в `cliniko.py` написан на веру, без документальной основы. Убрано из аргументации. |
| Cliniko webhooks покрывают services/practitioners | Даже если бы webhooks были — они покрывают только `patient.*` и `appointment.*`. Для RAG-данных (services, practitioners, business) polling всё равно нужен. |
| Entity Registry — оптимальное решение | **Over-engineering.** 3 новых таблицы + JSONPath + dual-write для 2 коннекторов и 3 сущностей — premature optimisation. |
| Pabau — "заглушка" | Частично верно, но формулировка вводит в заблуждение: `AbstractCrmConnector` спроектирован под Cliniko, а Pabau его наследует. Проблема в интерфейсе, не в Pabau. |
| Phase 2 (rename) — безболезненна | `ALTER TABLE ... RENAME` требует ACCESS EXCLUSIVE LOCK в PostgreSQL. Возможен downtime. Нельзя делать без zero-downtime стратегии. |
| Phase 4 (dual-write) — безопасна | SQL-запись и Chroma-индексация в разных транзакциях. Partial failure неизбежен. Восстановление не описано. |
| "Минимальные данные для RAG" — объективны | Субъективно. `online_bookable`, `website`, `title` — marked as "not needed" без обоснования. Агент может захотеть ответить на любой из этих вопросов. |

---

## 1. Терминология: PMS → HMS

Везде в коде используется **PMS** (Practice Management System).

**Решение: отложить.** Rename таблиц — высокий риск (locking БД), нулевая бизнес-ценность. Сделать при следующем breaking change (новый тип сущностей, новая миграция). Пока использовать `pms_*` как есть.

### Где нужно будет переименовать (когда придёт время)

| Область | Файлы |
|---------|-------|
| Таблицы БД | `pms_services`, `pms_practitioners`, `pms_clinic` — в моделях, миграциях |
| Модели | `models.py:490-533` — классы `PmsService`, `PmsPractitioner`, `PmsClinic` |
| Админ API | `knowledge/sync.py` — `/sync/crm`, `/sync/crm/reindex`, `/sync/crm/orphans`, `/sync/crm/status` |
| Core scheduler | `core/crm_sync.py`, `core/scheduler.py` — `poll_crm_changes()` |
| Shared field mappers | `shared/pms_fields.py` |
| RAG indexer | `rag/crm_indexer.py` — метаданные `source: "pms"` |
| События | `KbActivity.event_type` — `pms_synced` |
| Тесты | `test_pms_fields.py`, `test_admin_cliniko.py`, `test_admin_pabau.py` |

---

## 2. Текущая архитектура

### 2.1 Схема данных

**3 таблицы в БД** (одна для каждой группы данных):

```
pms_services          pms_practitioners      pms_clinic
──────────────────    ──────────────────     ────────────────
id (UUID PK)          id (UUID PK)           id (UUID PK)
tenant_id (FK)        tenant_id (FK)         tenant_id (FK)
external_id (text)    external_id (text)     external_id (text)
name                  display_name           business_name
description           title                  address
price_cents           designation            city
duration_minutes      description            state
category              active                 postcode
telehealth_enabled    raw_data (JSONB)       country
online_bookable                              phone
raw_data (JSONB)                             email
created_at                                    website
updated_at                                    timezone
                                              raw_data (JSONB)
                                              created_at
                                              updated_at
```

### 2.2 Коннекторы

```
Admin UI (integrations_hub.py)
       │
       ▼
Sync Layer (knowledge/sync.py + core/crm_sync.py)
       │
       ▼
┌─────────────────────────────┐
│   AbstractCrmConnector      │  ← 14 методов (patients, appointments,
│   ├── ClinikoConnector      │     practitioners, services, businesses,
│   └── PabauConnector        │     webhooks, slots)
└─────────────────────────────┘
       │
       ▼
┌─────────────────────────────┐
│  Storage:                    │
│  ├── SQL (pms_* tables)      │
│  └── Chroma (PMS chunks)     │
└─────────────────────────────┘
```

**Ключевые компоненты:**

| Компонент | Файл | Роль |
|-----------|------|------|
| Базовый класс | `integrations/base.py` | `AbstractCrmConnector` — 14 абстрактных методов |
| Cliniko | `integrations/cliniko.py` | REST API Cliniko, _paginate_all, enrich_services_with_descriptions |
| Pabau | `integrations/pabau.py` | REST API Pabau (get_businesses → [] — заглушка) |
| Resolver | `integrations/resolver.py` | Выбор коннектора по `tenant.crm_provider` |
| Field mappers | `shared/pms_fields.py` | `service_fields()`, `practitioner_fields()`, `clinic_fields()` + `upsert_objects()` |
| Sync API | `knowledge/sync.py` | 4 ручки: POST /sync/crm, POST /sync/crm/reindex, POST /sync/crm/orphans, GET /sync/crm/status |
| Background sync | `core/crm_sync.py` | `poll_crm_changes()` — инкрементальная синхронизация |
| Scheduler | `core/scheduler.py` | APScheduler, каждые 60 мин, только если WORKER_TYPE=scheduler |
| RAG indexer | `rag/crm_indexer.py` | Извлекает sections из PMS данных, chunking, отправка в Chroma |
| Webhooks | `integrations/webhooks.py` | POST /integrations/webhooks/{cliniko,pabau}/{tenant_id} — **только patient/appointment события** |

### 2.3 Webhooks: реальность

**Cliniko:** официальной поддержки webhooks нет. Код `verify_webhook_signature` и `parse_webhook_event` в `cliniko.py` написан без документального основания. Ни REST API docs, ни Help Center Cliniko не упоминают вебхуки.

**Pabau:** аналогично — `verify_webhook_signature` реализован, но документация не проверена.

**Текущая обработка** (`integrations/webhooks.py`): если webhook приходит — обрабатываются только `patient.*` и `appointment.*` события. Всё остальное логируется как "unhandled" и игнорируется.

**Вывод для RAG данных:** services, practitioners, clinic — **не покрываются webhooks** ни одной из систем (даже если webhooks есть). Polling — единственный надёжный механизм.

### 2.4 Текущие группы данных

| Группа | Cliniko источник | Pabau источник | Нужен webhook? | Нужен polling? |
|--------|-----------------|----------------|----------------|----------------|
| **Services** | `billable_items` + `appointment_types` → enrich | `get_services()` | Нет поддержки | ✅ Да |
| **Practitioners** | `practitioners` | `staff` | Нет поддержки | ✅ Да |
| **Clinic** | `businesses` | `[]` (заглушка) | Нет поддержки | ✅ Да |

### 2.5 Проблемы текущей архитектуры

1. **Три жёстко заданные группы** — не универсально. У Pabau могут быть `locations`, `departments`. Другие HMS — свои сущности.
2. **raw_data (JSONB) без схемы** — при переиндексации `raw_data` может не содержать ожидаемых полей, если HMS API изменился.
3. **Pabau — Cliniko-centric интерфейс.** `AbstractCrmConnector` спроектирован под Cliniko (patients, appointments, slots). Pabau наследует методы, которые не может имплементировать (`get_businesses → []`, `search_available_slots → NotImplementedError`).
4. **Нет версионирования схемы** — если HMS API меняется, `raw_data` может сломать реиндексацию.
5. **Нет webhook-стратегии для RAG-данных** — webhooks есть (или предполагаются) только для patients/appointments, но не для services/practitioners/clinic. Polling — единственный путь.

---

## 3. Универсальный подход: минимальное решение

Entity Registry (из v1) — over-engineering. Реальный подход проще.

### 3.1 Отказ от Entity Registry

Предлагавшееся решение (`hms_entity_types`, `hms_entity_fields`, `hms_entity_records`) неоправданно сложно:
- 3 новых таблицы на пустом месте
- JSONPath на каждый fetch
- Dual-write фаза с гарантированной рассинхронизацией
- Нет выгоды при текущем количестве коннекторов (2) и типов (3)

### 3.2 Альтернатива: гибкие существующие таблицы

```sql
-- 1. Добавить колонку entity_type в каждую таблицу (опционально)
ALTER TABLE pms_services ADD COLUMN entity_type VARCHAR(32) DEFAULT 'service';
ALTER TABLE pms_practitioners ADD COLUMN entity_type VARCHAR(32) DEFAULT 'practitioner';
ALTER TABLE pms_clinic ADD COLUMN entity_type VARCHAR(32) DEFAULT 'clinic';

-- 2. JSON schema validation для raw_data (опционально)
-- На уровне приложения: schema registry в Python
```

**Как это работает:**
- Если новый HMS добавляет entity type (например, `location`) — создаётся новая таблица `pms_locations` по аналогии
- Если новый HMS имеет другие поля — `raw_data` их сохраняет, field_map_fn маппит только известные
- Schema validation в Python (не в БД) для raw_data

### 3.3 Абстрактный `HmsConnector` (легковесный)

```python
class HmsConnector(ABC):
    provider: str

    @abstractmethod
    def fetch_services(self, updated_since: str | None = None) -> list[dict]: ...
    @abstractmethod
    def fetch_practitioners(self) -> list[dict]: ...
    @abstractmethod
    def fetch_clinics(self) -> list[dict]: ...

    @abstractmethod
    def test_connection(self) -> bool: ...
```

Три обязательных метода + test_connection. Ничего лишнего. Если HMS не поддерживает какой-то тип — возвращает пустой список (как Pabau с `get_businesses`).

### 3.4 ClinikoConnector → HmsConnector

Текущий `AbstractCrmConnector` (14 методов) остаётся для operational-задач (appointments, patients). Новый `HmsConnector` — только для RAG sync. ClinikoConnector наследует **оба** интерфейса:

```python
class ClinikoConnector(AbstractCrmConnector, HmsConnector):
    ...
```

---

## 4. Минимальные данные для RAG Knowledge Base

### 4.1 Что реально использует RAG

Текущий `crm_indexer.py` строит chunks из секций:

**Services**: Name, Pricing, Duration, Category, Description, Telehealth, Online booking, Code
**Practitioners**: Name, Title, Specialty, Description, Accepting new patients
**Clinic**: Clinic name, Address, Phone, Email, Website, Timezone, Additional info

### 4.2 Что минимально необходимо

| Сущность | Поле | Почему агенту важно |
|----------|------|---------------------|
| **Service** | `name` | Пациент: «что вы предлагаете?» |
| | `description` | Пациент: «что входит?», «какие противопоказания?» |
| | `price_cents` | Пациент: «сколько стоит?» |
| | `duration_minutes` | Пациент: «сколько времени?» |
| | `category` | Пациент: «какие есть массажи?» |
| | `telehealth_enabled` | Пациент: «можно онлайн?» |
| **Practitioner** | `display_name` | Пациент: «кто принимает?» |
| | `designation` | Специализация |
| | `description` | Биография, опыт |
| | `active` | Принимает ли сейчас |
| **Clinic** | `business_name` | Название |
| | `address` | Где находится |
| | `phone` | Контакт |
| | `timezone` | Часовой пояс |

### 4.3 Спорные поля (v1 ошибочно marked as "not needed")

| Поле | В v1 | Реальность |
|------|------|------------|
| `online_bookable` | Не нужно | **Нужно.** Пациент спросит «можно записаться онлайн». Решение: агент должен знать, есть ли онлайн-букинг. |
| `website` | Не нужно | **Спорно.** Агент может сказать «подробнее на сайте». Решение: включить, но низкий priority. |
| `title` (practitioner) | Дубликат `designation` | **Не дубликат.** Title = "Dr.", designation = "Cardiologist". Разные поля. |

**Правило:** все поля HMS — кандидаты на RAG. Решение об исключении принимается по метрикам (relevancy падает? → включить). Не субъективно.

---

## 5. Миграционный план (упрощённый)

### Phase 1: Сейчас
- 3 таблицы работают
- Cliniko connector работает
- Pabau connector работает (с ограничениями)
- Sync engine работает (polling 60 мин)

### Phase 2: Новый HmsConnector интерфейс
- Создать `HmsConnector` с 4 методами (fetch_services, fetch_practitioners, fetch_clinics, test_connection)
- ClinikoConnector наследует оба интерфейса
- PabauConnector наследует оба интерфейса (practitioners/services OK, clinics → [])
- Resolver переключить на HmsConnector для sync
- AbstractCrmConnector оставить для operational-задач
- **Rollback:** переключить resolver обратно

### Phase 3: Schema validation для raw_data
- Добавить `pms_field_schemas.json` (или config.yaml) — описание ожидаемых полей для каждого провайдера
- Перед canonicalization проверять raw_data по схеме
- Логировать предупреждения при несоответствии
- **Rollback:** убрать проверку

### Phase 4: Webhook bridge (опционально)
- Если подтвердится, что Cliniko/Pabau поддерживают webhooks для patients/appointments — оставить как есть
- Для services/practitioners/clinic — polling остаётся всегда
- **Rollback:** не добавлять

### ❌ Из v1 удалено
- **Entity Registry** — over-engineering, не делаем
- **Rename PMS→HMS** — отложено (риски > выгода)
- **Dual-write** — гарантированная рассинхронизация
- **5 фаз → 3 фазы**

---

## 6. Что делать с существующими данными

1. **Оставить как есть.** Три таблицы работают, миграция данных не нужна.
2. **Chroma метаданные** — `source: "pms"` остаётся. При добавлении нового провайдера — добавить `provider: "cliniko" | "pabau"`.
3. **Reindex endpoint** — переключить на новый HmsConnector в Phase 2.

---

## 7. UX/UI Analysis: Sync Section

### 7.1 Current state

Sync UI is split across **two pages**:

| Страница | Что показывает | Роль |
|----------|---------------|------|
| `/admin/integrations` (integrations_hub.html) | Карточки Cliniko/Pabau с статусом connected/not_configured | **Configure** — подключение/отключение HMS |
| `/admin/knowledge` (knowledge.html → tab "Practice Data") | 3 карточки (Services, Practitioners, Clinic) + Sync buttons + метрики | **Operate** — управление синхронизацией |

**Текущий user flow:**
1. Пользователь идёт в Integrations → подключает Cliniko (API key)
2. Переходит в Knowledge → вкладка Practice Data
3. Видит 3 карточки с кнопками Sync
4. Нажимает Sync (по одной или все сразу)
5. Статус обновляется через poll (каждые 30 сек)
6. Может нажать Reindex from SQL (с подтверждением)

### 7.2 Ключевые проблемы UX

#### 1. Две страницы для одного процесса
- **Интеграция** и **синхронизация** — части одного процесса, но разнесены в разные разделы
- Пользователь подключает Cliniko в Integrations, а управляет sync в Knowledge
- Нет прямой навигации Integrations → Practice Data и обратно

#### 2. Нет первого sync после подключения
- После успешного connect в Integrations → пользователь идёт в Knowledge и видит пустые карточки
- Sync по умолчанию не запускается автоматически
- Первый sync мог бы запуститься сразу после connect

#### 3. Нет прогресса sync-операции
- Только спиннер иконки + текст "Syncing all data…"
- Нет прогресс-бара (сколько из 100 services уже обработано)
- Нет ETA
- Если sync идёт долго (1000+ services) — пользователь не знает, работает ли система

#### 4. Ошибки не показываются пользователю
- `_setIcon(type, 'error')` ставит красный крестик, но **не показывает текст ошибки**
- `pmsDetail` в карточках пустой — поле есть в HTML (`class="pms-card-detail"`) но никогда не заполняется
- `renderCard()` передаёт `data.detail` но ответ API не содержит поле `detail`
- Пользователь видит только "Synced with errors" без указания причины

#### 5. Reindex from SQL — опасная операция без explainer
- Кнопка `Reindex from SQL` рядом с метриками без контекста
- Что делает? Зачем нужна? Когда нажимать?
- Confirm dialog: "Reindex all PMS data from SQL to Chroma? This will not call the CRM API." — это пользовательский, не технический термин

#### 6. Нет статуса "proxy" данных
- Непонятно, synced ли данные вообще (только по времени last sync)
- Нет метки "данные не synced X дней" или "требуется sync"
- Нет авто-sync триггера: если данных нет → предложить sync

#### 7. Нет preview данных
- Клик по карточке Service ничего не показывает
- Нет возможности посмотреть, какие именно services/practitioners засинканы
- Можно только доверять счётчику "42 services"

#### 8. Нет фильтрации по провайдеру
- Подключен и Cliniko и Pabau одновременно? (логически нельзя — только один провайдер на tenant)
- Но если в будущем tenant >1 провайдера — UI не готов

### 7.3 Стилистические проблемы

| Проблема | Описание |
|----------|----------|
| **PMS в названиях классов** | В HTML: `pms-header`, `pms-card`, `pms-spinner`, `pms-metrics`. Нужно переименовать в `hms-*` когда будет rename. |
| **Sync button — символ юникода** | `&#10227;` (⟳) неидеален. Лучше SVG-иконка sync. |
| **Card design flat** | Карточки сливаются с фоном. `border: 1px solid var(--border)` при `background: rgba(255,255,255,0.02)` — низкий контраст. |
| **Нет анимации состояний** | Переход idle→loading→success/error резкий. Нет плавной смены. |
| **Метрики в строку** | `pms-metrics` рендерит три числа в flex-row. При 3+ метриках — ломается на мобильных. |

### 7.4 User Scenarios & Improvements

#### Scenario 1: Новый пользователь подключает Cliniko впервые

**Сейчас:**
1. Integrations → Connect Cliniko → ввести API key → Connected
2. Знать, что надо идти в Knowledge → Practice Data
3. Нажать Sync All → ждать → "All data synced successfully"
4. Больше ничего не делать

**Проблемы:** Нет автоматического первого sync. Нет онбординга "что дальше". Пользователь может не знать про вкладку Practice Data.

**Решение:**
- После connect в Integrations → **авто-редирект** на Knowledge#practice
- Или **авто-запуск** первого sync
- Onboarding tooltip: "Ваши Services и Practitioners синхронизируются. Это может занять до 2 минут."

#### Scenario 2: Опытный пользователь проверяет статус sync

**Сейчас:**
- Видит только последнее время и количество chunks
- Нет информации: "изменилось ли что-то с прошлого sync?"

**Решение:**
- Добавить **diff-индикатор**: "+3 новых service", "2 practitioners удалены"
- Хранить snapshot предыдущего sync для сравнения
- Показывать изменения в карточке (например, зелёный "+3" рядом с count)

#### Scenario 3: Sync упал с ошибкой

**Сейчас:**
- Иконка → красный крестик
- "Synced with errors"

**Решение:**
- Кликабельная ошибка: развернуть detail
- Кнопка "Retry" на конкретной карточке (уже есть, но не подсвечена)
- Логирование ошибки в KbActivity

#### Scenario 4: Данные устарели

**Сейчас:**
- Polling раз в 30 секунд (вкладка открыта)
- Polling раз в 60 минут (scheduler в бэкграунде)

**Решение:**
- Показать warning на карточке: "Last synced 3 days ago. Data may be outdated."
- Кнопка "Sync now" сразу бросается в глаза
- Scheduled sync status: "Next auto-sync in 45 min"

### 7.5 Предлагаемые изменения UI

```
┌─────────────────────────────────────────────────────┐
│  📊 Practice Data Synced 2 min ago  [⟳ Sync All]   │
│  Cliniko · Last sync: today 14:23                   │
├─────────────┬──────────────┬────────────────────────┤
│  Services   │ Practitioners│  Clinic                │
│  ─────────  │ ───────────  │  ──────                │
│  [●] 42     │ [●] 5        │  [●] 1                 │
│  Last: 2m   │ Last: 2m     │  Last: 2m              │
│  +3 new     │  unchanged   │  unchanged             │
│  [⟳ Sync]   │ [⟳ Sync]    │  [⟳ Sync]             │
├─────────────┴──────────────┴────────────────────────┤
│  📈 Chunks: 1,248 total · 312 PMS · 936 KB         │
│  ⚠ 3 services failed to sync. [View errors →]      │
└─────────────────────────────────────────────────────┘
```

### 7.6 Priority Matrix

| Улучшение | Impact | Effort | Priority |
|-----------|--------|--------|----------|
| Auto-first-sync после connect | High | Low | P0 |
| Показывать текст ошибки в карточке | High | Low | P0 |
| Diff-индикатор (+N новых) | Medium | Medium | P1 |
| Preview данных (клик по карточке) | Medium | Medium | P1 |
| Onboarding tooltip для new users | Medium | Low | P1 |
| Progress bar для sync | Low | Medium | P2 |
| Warning об устаревших данных | Low | Low | P2 |
| SVG sync иконка вместо юникода | Low | Low | P2 |
| Анимация переходов состояний | Low | Low | P3 |

---

## 8. Выводы

1. **Текущая архитектура адекватна.** 3 таблицы + raw_data решают задачу. Не надо переусложнять.
2. **Entity Registry — premature optimisation.** Отказ от него — главное исправление v2.
3. **Webhooks для RAG-данных — несуществующий инструмент.** Только polling.
4. **Cliniko webhooks — неподтверждены.** Код написан на веру. Надо либо подтвердить тестовым Cliniko аккаунтом, либо удалить.
5. **PMS→HMS rename отложен.** Ноль бизнес-ценности, ненулевой риск.
