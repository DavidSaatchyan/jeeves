# Refactoring Plan: Appointments → Pass-Through Architecture

## 1. Problem Analysis

### Current Architecture
```
Patient ──▶ WhatsApp ──▶ AI Triage ──▶ Workflow ──▶ Local DB ──▶ Admin UI
                                                        │
                                           CRM Webhook ─┘ (sync)
```

Jeeves сегодня является **source of truth** для appointment-данных. Все операции (create, read, update, delete) идут напрямую в локальную БД. CRM-интеграция работает "задом наперёд": вебхуки из CRM синхронизируют данные в локальную таблицу.

### Проблемы

| Проблема | Описание | Severity |
|----------|----------|----------|
| **Два source of truth** | Данные хранятся и в CRM, и в Jeeves → конфликты, stale data | Critical |
| **HIPAA compliance** | Храним ePHI (patient_id, provider_name, reason, notes) в локальной БД → расширяем scope compliance | High |
| **Stale data** | Если CRM обновили запись, Jeeves узнаёт об этом только через вебхук (секунды-минуты) | High |
| **AI отвечает из кэша** | AI может сказать "у вас запись завтра в 14:00", а она уже отменена в CRM | Critical |
| **Sync complexity** | Вебхуки, retries, dedup, conflict resolution — сложная инфраструктура | Medium |
| **Admin UI может врать** | Показывает данные из локальной БД, которые могут отличаться от CRM | High |

### Root Cause

Модуль `core/booking/` и `admin/appointments.py` были написаны для сценария "у клиента нет CRM — Jeeves сам управляет расписанием". Но для клиентов с CRM (Zoho, HubSpot, Salesforce) это создаёт дублирование данных и все связанные проблемы.

---

## 2. Target Architecture

### Pass-Through с минимальным operational cache

```
Patient ──▶ WhatsApp ──▶ AI Triage ──▶ Workflow ──▶ CRM Connector ──▶ CRM (source of truth)
                        │                            │
                        ▼                            ▼
                  AppointmentCache           CRM Webhook
                  (local, minimal)           (cache invalidation)
                        │
                        ▼
                  Admin UI
                  (pass-through к CRM,
                   fallback на cache)
```

### Принципы

1. **CRM — единственный source of truth для appointment-данных**
2. **Jeeves хранит локально только operational state:**
   - `external_id` — ссылка на запись в CRM
   - `status` — кэшированный статус для AI workflow (с TTL)
   - `reminder_sent_24h`, `reminder_sent_2h` — state для напоминаний
   - `slot_token` — для оптимистичных блокировок при self-scheduling
   - `created_at`, `updated_at` — метаданные кэша
3. **Все CRUD операции — через CRM Connector (pass-through)**
4. **Admin UI читает данные через CRM Connector, не из локальной БД**
5. **Вебхуки из CRM — инвалидация кэша, не создание локальной копии**
6. **Booking engine — только для клиентов без CRM (опциональный режим)**

### Data Flow

#### Read (просмотр записи)
```
Admin UI ──▶ GET /admin/api/appointments/{id}
                │
                ├── CRM есть? ──▶ CRM Connector ──▶ CRM API ──▶ response
                │
                └── CRM нет?  ──▶ AppointmentCache ──▶ response
```

#### Write (создание/изменение)
```
Admin UI ──▶ POST /admin/api/appointments
                │
                ├── CRM есть? ──▶ CRM Connector ──▶ CRM API
                │                       │
                │                       ▼
                │                 Webhook ──▶ cache invalidation
                │
                └── CRM нет? ──▶ AppointmentCache (direct write)
```

#### AI Context (для ответа пациенту)
```
AI Workflow ──▶ нужен context appointment?
                    │
                    ├── CRM есть? ──▶ CRM Connector ──▶ CRM API (live)
                    │                       │
                    │                       ▼
                    │                 Cache result на 30-60s (in-memory)
                    │
                    └── CRM нет? ──▶ AppointmentCache (direct read)
```

---

## 3. Migration Strategy: Incremental, Safe

### Фазы

| Фаза | Что делаем | Риск | Тесты |
|------|-----------|------|-------|
| **Phase A** | Подготовка: модель AppointmentCache, CRM Connector read methods | Низкий | Все существующие тесты проходят |
| **Phase B** | Admin API → pass-through чтение через CRM Connector | Средний | Admin UI тесты с mock CRM |
| **Phase C** | Admin API → pass-through запись через CRM Connector | Средний | CRM adapter тесты |
| **Phase D** | AI Workflow → live чтение из CRM | Высокий | Booking E2E тесты |
| **Phase E** | Booking engine → dual-mode (CRM / local) | Средний | Все тесты |
| **Phase F** | Webhooks → cache invalidation (не upsert) | Низкий | CRM webhook тесты |
| **Phase G** | Cleanup: удалить старые поля из Appointment модели | Высокий | Alembic migration |
| **Phase H** | Testing & Polish | Низкий | Полный прогон |

---

## 4. Detailed File-by-File Changes

### Phase A: Подготовка модели и CRM Connector

#### `api/app/models.py` — Appointment → AppointmentCache

**Сейчас:** полноценная модель со всеми полями.

```python
class Appointment(Base):
    id = Column(UUID(...), primary_key=True)
    tenant_id = Column(...)
    patient_id = Column(...)
    external_id = Column(Text)           # CRM ID
    provider_name = Column(Text)         # ⛔ дубликат CRM
    provider_specialty = Column(Text)   # ⛔ дубликат CRM
    department = Column(Text)           # ⛔ дубликат CRM
    start_time = Column(DateTime)        # ⛔ дубликат CRM
    end_time = Column(DateTime)          # ⛔ дубликат CRM
    status = Column(String(32))          # ✅ operational (с TTL)
    reason = Column(Text)               # ⛔ дубликат CRM
    notes = Column(Text)                # ⛔ дубликат CRM
    source = Column(String(32))          # ? нужен?
    slot_token = Column(String(64))      # ✅ operational (для блокировок)
    reminder_sent_24h = Column(Boolean)  # ✅ operational
    reminder_sent_2h = Column(Boolean)   # ✅ operational
    consent_id = Column(UUID(...))       # ✅ compliance ref
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
```

**После:** минимальная cache-модель.

```python
class AppointmentCache(Base):
    """Local cache for appointment operational state.
    Source of truth is always the external CRM.
    """
    __tablename__ = "appointment_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True)
    external_id = Column(Text, nullable=False, index=True)  # CRM record ID

    # Operational state (NOT source of truth)
    status = Column(String(32), default="scheduled")        # cached for AI workflow
    slot_token = Column(String(64))                         # optimistic lock
    reminder_sent_24h = Column(Boolean, default=False)       # reminder state
    reminder_sent_2h = Column(Boolean, default=False)        # reminder state
    consent_id = Column(UUID(as_uuid=True), nullable=True)  # compliance ref
    source = Column(String(32), default="whatsapp")         # how it was created

    # Cache metadata
    cached_at = Column(DateTime, default=datetime.utcnow)
    last_synced_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
```

**Что останется в AppointmentCache:**
- `external_id` — ссылка на CRM
- `status` — для AI workflow (быстрый контекст без CRM API call)
- `slot_token` — для self-scheduling optimistic lock
- `reminder_sent_24h`, `reminder_sent_2h` — state напоминаний
- `consent_id` — compliance ref
- `source` — откуда создана запись

**Что уходит из локального хранения (теперь только в CRM):**
- `provider_name`, `provider_specialty`, `department`
- `start_time`, `end_time`
- `reason`, `notes`

#### `api/app/integrations/crm/base.py` — добавить read methods

**Сейчас:** в AbstractCrmConnector уже есть методы для appointments:
```python
def create_appointment(self, patient_id: str, data: dict) -> dict
def update_appointment(self, appt_id: str, data: dict) -> dict
def cancel_appointment(self, appt_id: str) -> bool
def get_patient_appointments(self, patient_id: str) -> list[dict]
def search_available_slots(self, doctor_id: str, date: str) -> list[dict]
```

**Нужно добавить:**
```python
@abstractmethod
def get_appointment(self, appt_id: str) -> dict[str, Any] | None:
    """Get single appointment by external ID."""
    ...

@abstractmethod
def list_appointments(
    self,
    tenant_id: str,
    status: str | None = None,
    provider: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    patient_id: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> dict:
    """List appointments with filters. Returns dict with total + items."""
    ...
```

#### `api/app/integrations/crm/zoho.py` — имплементировать read методы

**Сейчас:** есть `create_appointment`, `cancel_appointment`, `get_patient_appointments`, `search_available_slots`.

**Добавить:**
- `get_appointment()` — GET `/crm/v7/Appointments__s/{id}`
- `list_appointments()` — GET `/crm/v7/Appointments__s` с фильтрами

#### `api/app/integrations/crm/hubspot.py` — имплементировать read методы

**Сейчас:** только `create_appointment()` через Meetings.

**Добавить (или заглушить с raise "requires CRM with appointment module"):**
- `get_appointment()`
- `list_appointments()`
- `update_appointment()`

> **Решение:** HubSpot Meetings API не поддерживает полноценное управление appointment-данными (provider, time slot, reason). Для HubSpot connector оставить create через Meetings, read операции — заглушить с понятным сообщением.

#### `api/app/integrations/crm/salesforce.py` — запланировать имплементацию

**Сейчас:** все методы — stubs "Not implemented in Phase 3".

**Оставить как есть.** Appointments в Salesforce будут имплементированы, когда появится клиент с Salesforce Health Cloud.

---

### Phase B: Admin API — pass-through чтение

#### `api/app/admin/appointments.py` — рефакторинг роутов

**Принцип:** все read роуты проверяют, есть ли у tenant подключённый CRM. Если есть — читают через CRM Connector. Если нет — из AppointmentCache.

```python
def _has_crm(tenant_id: UUID, db: Session) -> bool:
    """Check if tenant has an active CRM connection."""
    from ..models import CrmConnection
    return db.query(CrmConnection).filter(
        CrmConnection.tenant_id == tenant_id,
        CrmConnection.is_active == True,
    ).first() is not None

def _get_crm_adapter(tenant_id: UUID, db: Session) -> AbstractCrmConnector | None:
    """Get CRM adapter for tenant, or None if no CRM connected."""
    conn = db.query(CrmConnection).filter(
        CrmConnection.tenant_id == tenant_id,
        CrmConnection.is_active == True,
    ).first()
    if not conn:
        return None
    from ...integrations.crm import get_crm_adapter
    return get_crm_adapter(conn.provider, conn.config)
```

**`GET /api/appointments` — pass-through:**
```python
@router.get("/api/appointments")
def list_appointments(
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
    status: str | None = Query(None),
    provider: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    patient_id: UUID | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    adapter = _get_crm_adapter(tenant.id, db)
    if adapter:
        # Pass-through to CRM
        result = adapter.list_appointments(
            tenant_id=str(tenant.id),
            status=status,
            provider=provider,
            date_from=date_from,
            date_to=date_to,
            patient_id=str(patient_id) if patient_id else None,
            offset=offset,
            limit=limit,
        )
        # Update local cache for status/slot_token (async or lazy)
        return result
    else:
        # No CRM — read from local AppointmentCache
        q = select(AppointmentCache).where(AppointmentCache.tenant_id == tenant.id)
        # ... (same as current but from cache table)
```

**`GET /api/appointments/{appointment_id}` — pass-through:**
```python
@router.get("/api/appointments/{appointment_id}")
def get_appointment(
    appointment_id: UUID,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    adapter = _get_crm_adapter(tenant.id, db)
    if adapter:
        # First look up external_id from cache
        cache = db.execute(
            select(AppointmentCache).where(
                AppointmentCache.id == appointment_id,
                AppointmentCache.tenant_id == tenant.id,
            )
        ).scalar_one_or_none()
        if not cache or not cache.external_id:
            raise HTTPException(status_code=404, detail="Appointment not found")
        # Pass-through to CRM
        result = adapter.get_appointment(cache.external_id)
        if not result:
            raise HTTPException(status_code=404, detail="Appointment not found in CRM")
        return _normalize_crm_appointment(result)
    else:
        # Read from local cache
        ...
```

#### `api/app/admin/appointments.py` — slot management

**`GET /api/appointments/slots` — без изменений для режима без CRM:**
- Для клиентов с CRM: `adapter.search_available_slots()`
- Для клиентов без CRM: текущий `get_available_slots()` из `core/booking`

**`GET /api/providers` — без изменений:**
- Провайдеры — это сущность, не обязательно связанная с CRM
- `Provider` model остаётся локальной (расписание врачей)

#### `api/app/admin/appointments.py` — response normalizer

```python
def _normalize_crm_appointment(data: dict) -> dict:
    """Normalize CRM appointment response to unified format."""
    return {
        "id": str(data.get("id", "")),
        "patient_id": str(data.get("patient_id", "")),
        "external_id": str(data.get("external_id", "")),
        "provider_name": data.get("provider_name", ""),
        "provider_specialty": data.get("provider_specialty"),
        "department": data.get("department"),
        "start_time": data.get("start_time"),
        "end_time": data.get("end_time"),
        "status": data.get("status", "scheduled"),
        "reason": data.get("reason"),
        "notes": data.get("notes"),
        "source": "crm_sync",
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
    }
```

---

### Phase C: Admin API — pass-through запись

#### `POST /api/appointments` — create

```python
@router.post("/api/appointments")
def create_appointment(
    body: _CreateAppointmentBody,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    adapter = _get_crm_adapter(tenant.id, db)
    if adapter:
        # Create in CRM
        crm_result = adapter.create_appointment(
            patient_id=str(body.patient_id),
            data={
                "provider_name": body.provider_name,
                "start_time": body.start_time.isoformat(),
                "end_time": body.end_time.isoformat(),
                "reason": body.reason,
                "source": body.source,
            },
        )
        # Create local cache entry
        cache = AppointmentCache(
            tenant_id=tenant.id,
            patient_id=body.patient_id,
            external_id=str(crm_result.get("id", "")),
            status="scheduled",
            source=body.source,
        )
        db.add(cache)
        db.commit()
        return _normalize_crm_appointment(crm_result)
    else:
        # No CRM — use existing booking engine
        from ..core.booking import book_appointment
        appt = book_appointment(db=db, tenant_id=tenant.id, ...)
        db.commit()
        return _appt_to_dict(appt)
```

#### `PATCH /api/appointments/{appointment_id}` — update

```python
@router.patch("/api/appointments/{appointment_id}")
def update_appointment(
    appointment_id: UUID,
    body: _UpdateAppointmentBody,
    tenant: Tenant = Depends(get_admin_tenant),
    db: Session = Depends(get_db),
):
    adapter = _get_crm_adapter(tenant.id, db)
    if adapter:
        cache = db.get(AppointmentCache, appointment_id)
        if not cache:
            raise HTTPException(status_code=404, detail="Appointment not found")
        crm_result = adapter.update_appointment(cache.external_id, body.model_dump(exclude_none=True))
        # Update local cache status
        if body.status:
            cache.status = body.status
        cache.updated_at = datetime.utcnow()
        db.commit()
        return _normalize_crm_appointment(crm_result)
    else:
        # Local update (existing logic)
        ...
```

#### `POST /api/appointments/{appointment_id}/cancel` — cancel

```python
@router.post("/api/appointments/{appointment_id}/cancel")
def cancel_appointment_endpoint(
    appointment_id: UUID,
    body: _CancelAppointmentBody,
    ...
):
    adapter = _get_crm_adapter(tenant.id, db)
    if adapter:
        cache = db.get(AppointmentCache, appointment_id)
        if not cache:
            raise HTTPException(status_code=404, ...)
        adapter.cancel_appointment(cache.external_id)
        cache.status = "cancelled"
        db.commit()
        return {"ok": True}
    else:
        # Local cancel (existing logic)
        ...
```

---

### Phase D: AI Workflow — live чтение из CRM

#### `api/app/core/workflows/appointment.py`

**Сейчас:** `_confirm_booking()` и `_cancel_booking()` напрямую работают с локальной БД через `book_appointment()` / `cancel_appointment()`.

**Нужно:** вместо прямого вызова `core/booking`:
1. Определить, есть ли у tenant CRM
2. Если есть — вызывать CRM Connector
3. После успеха в CRM — создать/обновить AppointmentCache
4. Если CRM нет — использовать текущий booking engine

```python
async def _confirm_booking(self, event: CanonicalEvent, db: Session) -> None:
    payload = event.payload or {}
    adapter = _get_crm_adapter(self.tenant_id, db)

    if adapter:
        # Create in CRM
        crm_result = adapter.create_appointment(
            patient_id=str(payload.get("patient_id")),
            data={
                "provider_name": payload.get("provider_name", ""),
                "start_time": payload.get("start_time").isoformat(),
                "end_time": payload.get("end_time").isoformat(),
                "reason": payload.get("reason"),
                "source": payload.get("source", "whatsapp"),
            },
        )
        # Create local cache
        cache = AppointmentCache(
            tenant_id=self.tenant_id,
            patient_id=payload.get("patient_id"),
            external_id=str(crm_result.get("id", "")),
            status="scheduled",
            slot_token=payload.get("slot_token", ""),
            source=payload.get("source", "whatsapp"),
        )
        db.add(cache)
        db.flush()
        await self.transition("BOOKED", event, db, reason=f"booked_in_crm_{cache.id}")
    else:
        # Local booking engine (existing logic)
        from ..booking import book_appointment
        appt = book_appointment(db=db, ...)
        await self.transition("BOOKED", event, db, reason=f"booked_locally_{appt.id}")
```

#### `api/app/core/ai/triage.py` — без изменений

Triage-агент не работает напрямую с appointment-данными. Он только классифицирует intent (book_appointment, cancel, reschedule). Изменения не требуются.

---

### Phase E: Booking Engine — dual-mode

#### `api/app/core/booking/slot_manager.py`

**Сейчас:** `get_available_slots()` читает `Provider` и `Appointment` из локальной БД.

**Нужно:**
- Для клиентов с CRM: вызывать `adapter.search_available_slots()`
- Для клиентов без CRM: текущая логика (генерация слотов из Provider.schedule)

```python
def get_available_slots(
    db: Session,
    tenant_id: UUID,
    provider_name: str | None = None,
    specialty: str | None = None,
    day: date | None = None,
    limit: int = 10,
) -> list[Slot]:
    adapter = _get_crm_adapter(tenant_id, db)
    if adapter:
        # Pass-through to CRM
        crm_slots = adapter.search_available_slots(
            doctor_id=provider_name or "",
            date=day.isoformat() if day else date.today().isoformat(),
        )
        return [_crm_slot_to_local(s) for s in crm_slots][:limit]
    else:
        # Local slot generation (existing logic)
        ...
```

#### `api/app/core/booking/scheduler.py`

**Нужно:** `book_appointment()`, `reschedule_appointment()`, `cancel_appointment()` должны работать в двух режимах.

**Вариант:** оставить `core/booking/scheduler.py` без изменений (он работает с Appointment моделью). Добавить слой адаптации в `core/booking/__init__.py`, который выбирает CRM или локальный engine.

```python
# core/booking/__init__.py

def book_appointment(
    db: Session,
    tenant_id: UUID,
    patient_id: UUID,
    slot_token: str,
    provider_name: str,
    start_time: datetime,
    end_time: datetime,
    reason: str | None = None,
    source: str = "whatsapp",
) -> Appointment | AppointmentCache:
    """Book appointment via CRM or local engine."""
    adapter = _get_crm_adapter(tenant_id, db)
    if adapter:
        crm_result = adapter.create_appointment(...)
        cache = AppointmentCache(
            external_id=crm_result["id"],
            status="scheduled",
            ...
        )
        db.add(cache)
        db.flush()
        return cache
    else:
        from .scheduler import book_appointment as _local_book
        return _local_book(db, tenant_id, patient_id, slot_token,
                          provider_name, start_time, end_time, reason, source)
```

---

### Phase F: Webhooks → Cache Invalidation

#### `api/app/integrations/crm/webhooks.py`

**Сейчас:** `_upsert_appointment()` создаёт/обновляет полную `Appointment` запись в локальной БД.

**Нужно:** вебхуки должны:
1. Найти `AppointmentCache` по `external_id`
2. Если найден — обновить `status` (для AI workflow) + `last_synced_at`
3. Если не найден — создать `AppointmentCache` (минимально)
4. NOTA BENE: не хранить `provider_name`, `start_time`, `end_time` и т.д.

```python
def _sync_appointment_from_webhook(
    db: Session, tenant_id: uuid.UUID, patient_id: uuid.UUID, data: dict[str, Any]
) -> AppointmentCache:
    external_id = str(data.get("id", ""))
    cache = db.query(AppointmentCache).filter(
        AppointmentCache.tenant_id == tenant_id,
        AppointmentCache.external_id == external_id,
    ).first()

    if cache:
        cache.status = data.get("status", cache.status)
        cache.last_synced_at = datetime.utcnow()
        cache.updated_at = datetime.utcnow()
    else:
        cache = AppointmentCache(
            tenant_id=tenant_id,
            patient_id=patient_id,
            external_id=external_id,
            status=data.get("status", "scheduled"),
            cached_at=datetime.utcnow(),
            last_synced_at=datetime.utcnow(),
        )
        db.add(cache)

    db.flush()
    return cache
```

---

### Phase G: Cleanup — Alembic Migration

#### Новая миграция: `rename_appointment_to_appointment_cache`

```python
# Шаги:
# 1. Создать таблицу appointment_cache
# 2. Скопировать operational поля из appointments → appointment_cache
# 3. Переименовать старую таблицу в appointments_archive (backup)
# 4. Обновить все REFERENCES/ForeignKeys
```

**Важно:** миграция должна быть non-destructive. Старые данные сохраняются в `appointments_archive`.

**Поля, которые переезжают:**
- `id` → `id`
- `tenant_id` → `tenant_id`
- `patient_id` → `patient_id`
- `external_id` → `external_id`
- `status` → `status`
- `slot_token` → `slot_token`
- `reminder_sent_24h` → `reminder_sent_24h`
- `reminder_sent_2h` → `reminder_sent_2h`
- `consent_id` → `consent_id`
- `source` → `source`
- `created_at` → `created_at`
- `updated_at` → `updated_at`

**Поля, которые остаются в архиве (больше не используются кодом):**
- `provider_name`
- `provider_specialty`
- `department`
- `start_time`
- `end_time`
- `reason`
- `notes`

---

### Phase H: Обновление тестов

#### `api/tests/test_booking_e2e.py`

**Что изменить:**
- `test_list_slots()` — добавить тест для CRM pass-through режима
- `test_create_appointment_success()` — добавить тест создания через CRM
- `test_update_appointment()` — добавить тест обновления через CRM
- `test_cancel_appointment()` — добавить тест отмены через CRM
- `TestAdminAuthGuard` — без изменений

**Новые тесты:**
- `test_crm_pass_through_read` — mock CRM adapter, проверить что Admin API вызывает adapter.list_appointments()
- `test_crm_pass_through_write` — mock CRM adapter, проверить что Admin API вызывает adapter.create_appointment()
- `test_fallback_to_local_when_no_crm` — без CRM connector, проверить что используется AppointmentCache

#### `api/tests/test_crm_webhooks.py`

**Что изменить:**
- `TestUpsertAppointment` — вместо `Appointment` теперь проверяет `AppointmentCache`
- `test_appointment_event()` — обновить assertion на AppointmentCache

#### `api/tests/test_crm_zoho.py`, `test_crm_hubspot.py`

**Что изменить:**
- Добавить тесты для `get_appointment()` и `list_appointments()` (новые методы)

---

## 5. Dependencies & Impact Analysis

### Прямые изменения (20 файлов)

| Файл | Phase | Изменения |
|------|-------|-----------|
| `models.py` | A | Переименовать Appointment → AppointmentCache, убрать дублируемые поля |
| `integrations/crm/base.py` | A | Добавить `get_appointment()`, `list_appointments()` |
| `integrations/crm/zoho.py` | A | Имплементировать `get_appointment()`, `list_appointments()` |
| `integrations/crm/hubspot.py` | A | Заглушить read методы |
| `integrations/crm/salesforce.py` | A | Без изменений |
| `integrations/crm/custom_api.py` | A | Имплементировать pass-through методы |
| `admin/appointments.py` | B, C | Pass-through для read/write |
| `admin/pages.py` | B | Без изменений |
| `core/booking/__init__.py` | E | CRM-aware entry point |
| `core/booking/scheduler.py` | E | Dual-mode book/reschedule/cancel |
| `core/booking/slot_manager.py` | E | Dual-mode get_available_slots |
| `core/workflows/appointment.py` | D | Pass-through CRM в workflow |
| `channels/whatsapp.py` | D | Без изменений (уже использует workflow) |
| `integrations/crm/webhooks.py` | F | Cache invalidation вместо upsert |
| `templates/appointments.html` | B | Без изменений (UI не меняется) |
| `templates/base.html` | — | Без изменений |
| `templates/agents.html` | — | Без изменений |
| `templates/compliance.html` | — | Без изменений |
| `templates/connections.html` | — | Без изменений |
| `alembic/versions/faa41bd54658_*.py` | G | Новая миграция |

### Косвенные изменения (тесты, 9 файлов)

| Файл | Phase | Изменения |
|------|-------|-----------|
| `test_booking_e2e.py` | H | Dual-mode тесты |
| `test_crm_webhooks.py` | F, H | AppointmentCache вместо Appointment |
| `test_crm_zoho.py` | A, H | Новые методы connector |
| `test_crm_hubspot.py` | A, H | Заглушки read методов |
| `test_crm_base.py` | A | Сигнатуры новых методов |
| `test_crm_factory.py` | A | Mock новых методов |
| `test_whatsapp_webhook.py` | D | Без изменений |
| `test_compliance_*.py` | — | Без изменений |
| `test_knowledge.py` | — | Без изменений |

---

## 6. Rollback Plan

Если после деплоя возникает проблема:

1. **Каждая фаза — отдельный коммит** → можно откатить конкретную фазу `git revert <commit>`
2. **Feature flag** `USE_CRM_PASSTHROUGH` в `config.yaml`:
   ```yaml
   appointments:
     pass_through: true   # false = legacy local mode
   ```
3. **Старая таблица `appointments` не удаляется 30 дней** → переименовывается в `appointments_archive`
4. **Если CRM недоступен** → автоматический fallback на AppointmentCache + stale data

---

## 7. Timeline Estimate

| Phase | Что | Зависит от | Оценка |
|-------|-----|-----------|--------|
| A | Model + CRM Connector | — | 2-3 дня |
| B | Admin API pass-through read | A | 1-2 дня |
| C | Admin API pass-through write | A, B | 1-2 дня |
| D | AI Workflow pass-through | A, C | 2-3 дня |
| E | Booking engine dual-mode | A, D | 2 дня |
| F | Webhooks → cache invalidation | A | 1 день |
| G | Alembic migration | A-F | 1 день |
| H | Testing & Polish | A-G | 2-3 дня |
| | **Total** | | **12-17 дней** |

---

## 8. Appendix: Flow Diagrams

### Admin UI — List Appointments (pass-through)

```
User clicks Appointments
    │
    ▼
GET /admin/api/appointments?date_from=...&status=...
    │
    ├── has CRM?
    │   ├── YES ──▶ CRM Connector.list_appointments()
    │   │              │
    │   │              ├── Zoho: GET /crm/v7/Appointments__s?$filter=...
    │   │              ├── HubSpot: raise "not supported for HubSpot"
    │   │              └── Custom: GET /appointments?date_from=...
    │   │
    │   └── NO  ──▶ SELECT * FROM appointment_cache
    │                   WHERE tenant_id = ?
    │
    ▼
Return normalized response to Admin UI
```

### WhatsApp Self-Booking (pass-through)

```
Patient: "I want to book an appointment"
    │
    ▼
WhatsApp Webhook ──▶ CanonicalEvent(patient_message_received)
    │
    ▼
AppointmentWorkflow.handle_event()
    │
    ├── _confirm_booking()
    │   ├── has CRM?
    │   │   ├── YES ──▶ CRM Connector.create_appointment()
    │   │   │              │
    │   │   │              ▼
    │   │   │          AppointmentCache.create(external_id=CRM_id)
    │   │   │
    │   │   └── NO  ──▶ core/booking/book_appointment() → Appointment model
    │   │
    │   ▼
    │   transition("BOOKED")
    │
    ▼
Send confirmation to patient via WhatsApp
```

### CRM Webhook → Cache Invalidation

```
CRM (Zoho): Appointments__s.edit
    │
    ▼
POST /integrations/webhooks/zoho
    │
    ├── verify signature
    │
    ▼
_handle_webhook()
    │
    ├── parse event → {event_type: "appointment", "id": "...", "status": "cancelled"}
    │
    ▼
_sync_appointment_from_webhook()
    │
    ├── Find AppointmentCache by external_id
    │   ├── Found? → Update status + last_synced_at
    │   └── Not found? → Create minimal AppointmentCache
    │
    ▼
Return 200 OK
```

---

*План составлен на основе исследования best practices: pass-through architecture для AI/workflow систем (Unified.to, Truto, 2026), данных API-платформ и HIPAA/GDPR compliance requirements.*
