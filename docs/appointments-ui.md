# Appointments UI — Architecture & Implementation

> **Date**: 2026-06-01  
> **Scope**: Full-stack: template → JS → API routes → CRM/local fallback  
> **Status**: 467 tests pass, **all 3 bugs fixed** ✅

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                   base.html (shared layout)                  │
│  - api() fetch wrapper (auth, error handling)               │
│  - Sidebar navigation, shared CSS                           │
│  - Token management (localStorage)                          │
└──────────────────────────┬──────────────────────────────────┘
                           │ extends
                           ▼
┌──────────────────────────────────────────────────────────────┐
│              appointments.html (inline JS + CSS)              │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  {% block body %} — HTML structure                    │    │
│  │  ├── Stats cards (#apptStats)                        │    │
│  │  ├── Filter bar (date, status, provider, view mode) │    │
│  │  ├── Calendar grid (#calGrid) — week/month views    │    │
│  │  ├── Appointments table (.appt-table)                │    │
│  │  ├── Pagination (#apptPagination)                    │    │
│  │  ├── Create modal (#createModal)                     │    │
│  │  └── Detail modal (#detailModal)                     │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  {% block tail %} — inline <style> + <script>         │    │
│  │  ├── Calendar grid CSS (week/month)                  │    │
│  │  ├── Table CSS                                       │    │
│  │  └── All JS functions (vanilla, no framework)        │    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────┬───────────────────────────────────┘
                           │
        ┌──────────────────┼─────────────────────┐
        ▼                  ▼                     ▼
┌───────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ loadProviders │  │ loadAppointments │  │ Create/Update/   │
│ GET /admin/   │  │ GET /admin/api/  │  │ Detail actions   │
│ api/providers │  │ appointments     │  │                  │
└───────┬───────┘  └────────┬─────────┘  └────────┬─────────┘
        │                   │                      │
        ▼                   ▼                      ▼
┌──────────────────────────────────────────────────────────────┐
│               FastAPI Router (admin/appointments.py)          │
│                                                              │
│  ┌─────────────────────┐    ┌──────────────────────────┐     │
│  │  CRM Connected?     │───▶│  CRM Adapter (pass-through)│    │
│  │  (_get_crm_adapter) │    │  - ZohoCRMAdapter        │     │
│  │                     │    │  - CustomApiAdapter       │     │
│  └──────────┬──────────┘    │  - HubSpotAdapter(stub)   │     │
│             │ No            └────────────┬─────────────┘     │
│             ▼                            │                    │
│  ┌─────────────────────┐    ┌────────────┴─────────────┐     │
│  │ Local DB (Appointment│   │ CRM external API call     │     │
│  │ or AppointmentCache) │   │ (HTTP to Zoho/Custom)    │     │
│  └─────────────────────┘    └──────────────────────────┘     │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. API Route Table

### 2.1 Page Route

| Method | Path | Handler | Auth | Response |
|--------|------|---------|------|----------|
| GET | `/admin/appointments` | `pages.py:appointments_page` | `get_admin_tenant` | HTML (`appointments.html`) |

### 2.2 Data API Routes

| # | Method | Path | Function | Params | Non-CRM Response | CRM Response |
|---|--------|------|----------|--------|------------------|--------------|
| 1 | GET | `/admin/api/appointments` | `list_appointments` | `status`, `provider`, `date_from`, `date_to`, `patient_id`, `offset`, `limit` | `{total, offset, limit, appointments}` | `{total, offset, limit, appointments}` ✅ |
| 2 | GET | `/admin/api/appointments/slots` | `available_slots` | `provider_name`, `specialty`, `date` | `{slots}` | `{slots}` ✅ |
| 3 | GET | `/admin/api/appointments/{id}` | `get_appointment` | — | `_appt_to_dict()` | `_normalize_crm_appointment()` ✅ |
| 4 | POST | `/admin/api/appointments` | `create_appointment` | body: `{patient_id, provider_name, start_time, end_time, reason?, source?}` | `_appt_to_dict()` | `_normalize_crm_appointment()` ✅ |
| 5 | PATCH | `/admin/api/appointments/{id}` | `update_appointment` | body: `{status?, start_time?, end_time?, provider_name?, notes?, reason?}` | `_appt_to_dict()` | `_normalize_crm_appointment()` ✅ |
| 6 | POST | `/admin/api/appointments/{id}/cancel` | `cancel_appointment_endpoint` | body: `{reason?}` | `{"ok": True}` | `{"ok": True}` ✅ |
| 7 | GET | `/admin/api/providers` | `list_providers` | `specialty` | `{providers}` | N/A (no CRM variant) ✅ |

---

## 3. Response Format Details

### 3.1 `GET /admin/api/appointments` — Fixed ✅

**Was**: CRM path returned `{total, items}` → JS reads `d.appointments` → empty table.
**Now**: Both paths return `{total, offset, limit, appointments}` with normalized items via `_normalize_crm_appointment()`.

| Field | Non-CRM | CRM |
|-------|---------|-----|
| `total` | `int` | `int` |
| `offset` | `int` | `int` |
| `limit` | `int` | `int` |
| container | `appointments` | `appointments` |
| items | `_appt_to_dict()` | `_normalize_crm_appointment()` |

### 3.2 `GET /admin/api/appointments/{id}` — Consistent

Both paths return compatible shapes:

| Field | Non-CRM (`_appt_to_dict`) | CRM (`_normalize_crm_appointment`) |
|-------|--------------------------|-----------------------------------|
| `id` | `str(a.id)` | `str(data.get("id", ""))` |
| `patient_id` | `str(a.patient_id)` | `str(data.get("patient_id", ""))` |
| `external_id` | `a.external_id` | `str(data.get("external_id", ""))` |
| `provider_name` | `a.provider_name` | `data.get("provider_name", "")` |
| `provider_specialty` | `a.provider_specialty` | `data.get("provider_specialty")` |
| `department` | `a.department` | `data.get("department")` |
| `start_time` | `a.start_time.isoformat()` | `data.get("start_time")` |
| `end_time` | `a.end_time.isoformat()` | `data.get("end_time")` |
| `status` | `a.status` | `data.get("status", "scheduled")` |
| `reason` | `a.reason` | `data.get("reason")` |
| `notes` | `a.notes` | `data.get("notes")` |
| `source` | `a.source` | **`"crm_sync"`** (hardcoded) |
| `created_at` | `a.created_at.isoformat()` | `data.get("created_at")` |
| `updated_at` | `a.updated_at.isoformat()` | `data.get("updated_at")` |

Non-CRM **only**: `tenant_id`, `reminder_sent_24h`, `reminder_sent_2h` (not read by JS).

### 3.3 `POST /admin/api/appointments` — Consistent

Both paths return the same shape (via `_normalize_crm_appointment` or `_appt_to_dict`).  
Minor inconsistency: CRM path hardcodes `source: "crm_sync"` in response, non-CRM returns whatever was stored.

### 3.4 `PATCH /admin/api/appointments/{id}` — Fixed ✅

**Was**: CRM returned `{"ok": True}`, non-CRM returned `_appt_to_dict()`.
**Now**: Both paths return `_normalize_crm_appointment()` — consistent shape.

---

## 4. JavaScript Function Reference

All JS in `appointments.html` lines 132–482, vanilla ES6, no framework.

### 4.1 Core Functions

| Function | Lines | Purpose | API Call |
|----------|-------|---------|----------|
| `api(path, opts)` | `base.html:264` | Global fetch wrapper | — |
| `esc(v)` | 133 | HTML-escape string | — |
| `fmtDate(d)` | 139 | `Date` → `YYYY-MM-DD` | — |
| `getDateRange()` | 141–156 | Range for current view | — |
| `setView(v)` | 158–162 | Switch day/week/month | ⟶ `loadAppointments()` |
| `navDate(dir)` | 164–170 | Navigate calendar | ⟶ `loadAppointments()` |
| `todayDate()` | 172–176 | Jump to today | ⟶ `loadAppointments()` |
| `onDatePick()` | 178–182 | Date input changed | ⟶ `loadAppointments()` |

### 4.2 Data Loading

| Function | Lines | Purpose | API Call |
|----------|-------|---------|----------|
| `loadProviders()` | 189–207 | Fill provider dropdowns | **GET** `/admin/api/providers` |
| `loadAppointments(page)` | 212–237 | Main data fetch + render | **GET** `/admin/api/appointments?...` |

### 4.3 Rendering

| Function | Lines | Purpose |
|----------|-------|---------|
| `statusColor(s)` | 239–246 | Status → CSS color |
| `renderCalendarGrid(d)` | 249–332 | Week/month grid + stats |
| `statusPill(s)` | 334–342 | Status → HTML pill badge |
| `renderAppointments(d, page)` | 344–384 | Table rows + stats + pagination |

### 4.4 CRUD Actions

| Function | Lines | Purpose | API Call |
|----------|-------|---------|----------|
| `showCreateModal()` | 387–396 | Show create form | — |
| `closeModal(id)` | 398–400 | Hide modal | — |
| `createAppointment()` | 402–423 | Submit new appointment | **POST** `/admin/api/appointments` |
| `showDetail(id)` | 426–466 | View/edit single appointment | **GET** `/admin/api/appointments/{id}` |
| `updateStatus(id, status)` | 468–476 | Change status | **PATCH** `/admin/api/appointments/{id}` |

### 4.5 Init

```javascript
loadProviders();
document.getElementById('calRange').textContent = getDateRange().label;
loadAppointments();
```

### 4.6 Data Flow: `loadAppointments()`

```
loadAppointments(page?)
    │
    ├── getDateRange() → {from, to, label}
    │
    ├── Build query:
    │   /admin/api/appointments
    │   ?limit=200&offset=0
    │   &date_from={from}T00:00:00&date_to={to}T23:59:59
    │   &status={filter}&provider={filter}
    │
    ├── api(url) → GET
    │   │
    │   ├── CRM? → adapter.list_appointments() → {total, offset, limit, appointments} ✅
    │   └── No CRM? → Appointment.query → {total, offset, limit, appointments} ✅
    │
    ├── day view? → renderAppointments(d, page)
    │   └── d.appointments → table rows + stats + pagination
    │                         ├── time (start_time.slice(11,16))
    │                         ├── patient ID (slice(0,8)+"...")
    │                         ├── provider name
    │                         ├── reason
    │                         ├── department
    │                         ├── status pill
    │                         ├── source
    │                         └── "View" button → showDetail(id)
    │
    └── week/month? → renderCalendarGrid(d) + renderAppointments(d, page)
        └── d.appointments → 7-column grid / month grid
                              └── dots/labels grouped by date
```

---

## 5. Styling

### 5.1 Dependencies

| Source | Type | Used By |
|--------|------|---------|
| `base.html` `<style>` (lines 11–256) | Inline CSS | Shared variables, layout, buttons, forms, pills, modals |
| `appointments.html` `<style>` (lines 103–131) | Inline CSS | Calendar grid, table |
| Google Fonts: Inter 400–800 | External link | `base.html:9` |

### 5.2 No External CSS Files

The appointments page uses zero external stylesheets. The only CSS file in the project (`inbox.css`) is loaded exclusively by the inbox page.

### 5.3 Key CSS Classes

| Class | File:Line | Purpose |
|-------|-----------|---------|
| `.stats`, `.stat` | base.html:107 | Stats cards |
| `.card` | base.html:61 | Content wrapper |
| `.pill` variants | base.html:98 | Status badges |
| `.modal-overlay`, `.modal` | base.html:185 | Modal dialogs |
| `.flex`, `.gap-sm` | base.html:129 | Layout utilities |
| `.appt-table` | appts.html:104 | Appointment table |
| `.cal-week-header`, `.cal-week-body` | appts.html:111 | Week grid |
| `.cal-month-grid`, `.cal-month-cell` | appts.html:122 | Month grid |
| `.cal-appt-dot`, `.cal-appt-label` | appts.html:119 | Calendar dots |

---

## 6. Compatibility Issues: Complete List

### CRITICAL — ALL FIXED ✅

| # | Issue | Location | Status |
|---|-------|----------|--------|
| **1** | **CRM list → `items` vs `appointments`** | `admin/appointments.py:94-106` | **FIXED** — now wraps in `appointments` key |
| **2** | **No normalization on CRM list items** | `admin/appointments.py:94-106` | **FIXED** — each item goes through `_normalize_crm_appointment()` |

### MODERATE

| # | Issue | Description | Status |
|---|---------|-------------|--------|
| 3 | Pagination params passed to CRM but adapter applies offset/limit client-side (inefficient) | Still open |
| 4 | Provider list is always local DB — CRM-synced providers won't appear in dropdown |
| 5 | Race condition: `newProvider` dropdown empty if `loadProviders()` hasn't completed |
| 6 | No validation: `end_time > start_time`, UUID format, etc. |

### MINOR

| # | Issue | Description |
|---|---------|-------------|
| 7 | Inline `style=` attributes throughout (hard to theme) |
| 8 | Hardcoded `limit=200` regardless of calendar view |
| 9 | Patient UUID truncated to 8 chars in table |
| 10 | No retry/fallback if `loadProviders()` fails |
| 11 | Source field inconsistency: CRM hardcodes `"crm_sync"`, non-CRM stores actual source |
| 12 | Dedicated `POST /cancel` endpoint exists but UI uses `PATCH {status: "cancelled"}` |
| 13 | Day view hides calendar grid entirely (shows only table) |

---

## 7. Fix Plan — Status

| # | Priority | Fix | Status |
|---|----------|-----|--------|
| 1 | CRITICAL | Normalize CRM list response (`items` → `appointments`) | **DONE** ✅ |
| 2 | CRITICAL | Normalize individual list items through `_normalize_crm_appointment()` | **DONE** ✅ |
| 3 | MODERATE | PATCH response consistency (`{"ok": True}` → `_normalize_crm_appointment()`) | **DONE** ✅ |
| 4 | MINOR | UI form validation (date ordering, UUID format) | Open |
| 5 | MINOR | Provider dropdown fallback when `loadProviders()` fails | Open |

---

## 8. File Dependency Map

```
templates/appointments.html
  ├── extends templates/base.html
  │     ├── Google Fonts (Inter)
  │     ├── api() helper (lines 264–275)
  │     ├── token management (localStorage)
  │     └── Sidebar nav with /admin/appointments link
  │
  ├── {% block body %} — HTML (lines 1–100)
  │     ├── Stats cards (#apptStats)
  │     ├── Filter bar (date, status, provider, view toggle)
  │     ├── Calendar grid (#calGrid)
  │     ├── Table (.appt-table > #apptTbody)
  │     ├── Pagination (#apptPagination)
  │     ├── Create modal (#createModal)
  │     └── Detail modal (#detailModal)
  │
  └── {% block tail %} — CSS + JS (lines 102–483)
        ├── <style> calendar + table CSS (30 rules)
        └── <script> all JS (350 lines)

admin/pages.py:88
  └── @router.get("/appointments")
        └── render "appointments.html"

admin/appointments.py:82
  └── @router.get("/api/appointments")
        ├── CRM → adapter.list_appointments() → normalize → {total, offset, limit, appointments} ✅
        └── No CRM → Appointment.query → {total, appointments}

admin/appointments.py:202
  └── @router.get("/api/appointments/{id}")
        ├── CRM → AppointmentCache → adapter.get_appointment() → _normalize_crm_appointment() ✅
        └── No CRM → Appointment.query → _appt_to_dict() ✅

admin/appointments.py:234
  └── @router.post("/api/appointments")
        ├── CRM → adapter.create_appointment() → create cache → _normalize_crm_appointment() ✅
        └── No CRM → core/booking.book_appointment() → _appt_to_dict() ✅

admin/appointments.py:284
  └── @router.patch("/api/appointments/{id}")
        ├── CRM → AppointmentCache → adapter.update_appointment() → _normalize_crm_appointment() ✅
        └── No CRM → Appointment.query → _appt_to_dict() ✅

admin/appointments.py:333
  └── @router.post("/api/appointments/{id}/cancel")
        ├── CRM → AppointmentCache → adapter.cancel_appointment() → {"ok": True} ✅
        └── No CRM → core/booking.cancel_appointment() → {"ok": True} ✅

admin/appointments.py:360
  └── @router.get("/api/providers")
        └── Provider.query → {providers} (no CRM variant)
```

---

## 9. Test Coverage

| Test File | Tests | Covers |
|-----------|-------|--------|
| `tests/test_booking_e2e.py` | 51 tests | All admin API routes (list, slots, get, create, update, cancel) in both CRM and non-CRM modes |
| `tests/test_crm_zoho.py` | 7 new tests | `get_appointment()` and `list_appointments()` adapter methods |
| `tests/test_crm_hubspot.py` | 2 new tests | Stub methods raise `CrmConnectionError` |
| `tests/test_crm_base.py` | 2 tests | Abstract method signatures |
| `tests/test_crm_factory.py` | 1 test | `_MockAdapter` has both methods |
| `tests/test_crm_webhooks.py` | 1 class | `TestSyncAppointmentFromWebhook` with `AppointmentCache` |

**Current total: 467 tests passing, 0 failing.**

---

## 10. Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-06-01 | Phase A: AppointmentCache model, abstract connector methods, adapter implementations | — |
| 2026-06-01 | Phase B: Admin API read pass-through (`_has_crm`, `_get_crm_adapter`, `_normalize_crm_appointment`) | — |
| 2026-06-01 | Phase C: Admin API write pass-through (create/update/cancel) | — |
| 2026-06-01 | Phase D: AI Workflow CRM-aware `_confirm_booking` / `_cancel_booking` | — |
| 2026-06-01 | Phase E: Booking engine dual-mode (`__init__.py`, `slot_manager.py`) | — |
| 2026-06-01 | Phase F: Webhooks cache invalidation (`_sync_appointment_from_webhook`) | — |
| 2026-06-01 | Phase G: Alembic migration `b2c3d4e5f6a7` (appointment_cache table, appointments archive) | — |
| 2026-06-01 | Phase H: 7 CRM pass-through tests + 9 connector tests (zoho, hubspot) | — |
| 2026-06-01 | Bug found: CRM list response key `items` vs `appointments` (critical) | — |
| 2026-06-01 | Fix 1+2: CRM list normalizes `items` → `appointments` key with `_normalize_crm_appointment()` per item | — |
| 2026-06-01 | Fix 3: PATCH CRM path returns `_normalize_crm_appointment()` instead of `{"ok": True}` | — |
| 2026-06-01 | Doc updated: all bugs marked FIXED, status line updated | — |
