# Jeeves Rebrand: Medical Clinic Communication Platform

> **Date:** 2026-05-31
> **ICP:** Medical clinics in EU, US, and other regions

## 1. New Product Concept

### Core Value Proposition
An AI-powered communication platform for medical clinics that connects WhatsApp with the clinic's CRM to automate patient communication, appointment booking, marketing, and sales workflows.

### Primary Flow
```
Patient (WhatsApp) → AI Agent → Intent Classification → CRM Integration
                                                         ├── Appointment Booking
                                                         ├── Marketing/Sales Funnel
                                                         ├── Reminders & Follow-ups
                                                         └── Human Handoff (escalation)
```

### Key Features
| Feature | Priority | Description |
|---------|----------|-------------|
| WhatsApp Channel | P0 | Full WhatsApp Business API integration — messaging, templates, flows, rich media |
| CRM Integration | P0 | Connect with popular clinic CRMs or custom CRM APIs |
| Appointment Booking | P0 | AI-driven scheduling with slot management, reminders, rescheduling |
| Marketing/Sales Funnels | P1 | Triggered campaigns, personalized comms, lead qualification |
| Analytics | P1 | Conversion tracking, response time, automation ROI |
| Widget Channel | P1 | Website embed for initial contact before WhatsApp |
| Compliance | P0 | GDPR (EU), HIPAA-ready (US) — PHI minimization, consent management, audit logs |

## 2. Current vs Target State

### What to KEEP (core infrastructure)

| Module | Reason | Changes Needed |
|--------|--------|----------------|
| `auth/` | Auth system works — JWT, tenants, registration | Minimal — add GDPR consent fields |
| `admin/` | Admin panel — inbox, channels, connections, settings, knowledge | Refactor to remove "Shopify", "WISMO", "billing" references |
| `channels/widget.py` | Website widget — patient intake entry point | Reframe for clinic context (remove e-commerce terms) |
| `channels/registry.py` | Channel cache + status system | Keep — add WhatsApp to registry |
| `core/ai/` | LLM classification + generation | Reuse — retrain intents for medical domain |
| `core/memory.py` | Conversation history | Keep as-is |
| `core/timeline/` | Audit trail | Keep — critical for compliance |
| `rag/` | RAG engine — documentation search | Keep — for medical knowledge base |
| `knowledge/` | File management + product catalog | Reframe catalog for services/procedures |
| `shared/` | Locks, idempotency, inbox_writer, queue | Keep all — essential for reliability |
| `integrations/credentials.py` | Connector credential management | Keep — adapt for CRM providers |
| `models.py` | ORM models | Strip e-commerce fields, add medical models |
| `config.py` | Settings + YAML config | Strip Shopify, add CRM/compliance settings |
| `main.py` | FastAPI entrypoint | Minimal changes — remove old router references |
| Templates (`base`, `login`, `inbox`, `knowledge`) | Core UI | Reframe terminology |
| `schemas.py` | Pydantic models | Strip e-commerce, add medical |

### What to REMOVE (shopify/e-commerce)

| Module | Reason |
|--------|--------|
| `integrations/shopify/` | Entire Shopify integration — client, actions, events |
| `integrations/email/` | Email channel (SendGrid/Resend) — WhatsApp replaces |
| `integrations/webhooks.py` | Shopify webhook receiver — CRM webhooks replace |
| `integrations_routes.py` | Shopify/Rest test endpoints |
| `core/commerce/` | `billing.py`, `customer.py`, `subscription.py` — e-commerce concepts |
| `core/workflows/wismo.py` | WISMO workflow — order tracking for e-commerce |
| `core/workflows/wismo_service.py` | Shopify service layer for WISMO |
| `core/execution/` | Action dispatch system (unused by active paths) |
| `core/escalations/` | Escalation manager (too coupled to e-commerce — rebuild for medical) |
| `workers/` | Background workers (not wired in current setup) |
| `shared/queue.py` | Unused queue system |
| `channels/base.py` | Abstract channel (unused by concrete channels) |
| `channels/rest.py` | Placeholder REST channel |
| `core/policies/engine.py` + sub-modules | Policy engine — rebuild for medical rules |
| `core/events/dispatcher.py` | Event dispatch — rebuild for medical events |
| `channels/whatsapp.py` | Stub — rebuild properly for WhatsApp Business API |
| `config.py` → `shopify_shop`, `shopify_access_token` fields | Shopify env vars |
| Models → `shopify_customer_id`, `product_id`, e-commerce fields | Strip from ORM |

### What to ADD (medical/clinic)

| Module | Description |
|--------|-------------|
| `integrations/crm/` | CRM connector framework — providers: Zoho, HubSpot, Salesforce, Custom API |
| `integrations/crm/zoho.py` | Zoho CRM adapter (PHI-compatible, BAA available) |
| `integrations/crm/hubspot.py` | HubSpot CRM adapter (non-PHI marketing) |
| `integrations/crm/salesforce.py` | Salesforce Health Cloud adapter (enterprise) |
| `integrations/crm/base.py` | Abstract CRM connector interface |
| `core/booking/` | Appointment scheduling engine |
| `core/booking/scheduler.py` | Slot management, conflict resolution |
| `core/booking/calendar_sync.py` | Bi-directional calendar sync (Google, Outlook) |
| `core/booking/reminders.py` | Smart reminders with consent tracking |
| `core/compliance/` | GDPR/HIPAA compliance layer |
| `core/compliance/consent.py` | Consent capture, storage, renewal, revocation |
| `core/compliance/phi_minimization.py` | PHI stripping, tokenized links |
| `core/compliance/audit.py` | Extended audit logging for compliance |
| `core/compliance/retention.py` | Data retention policy enforcement |
| `core/workflows/appointment.py` | Appointment booking workflow (replaces WISMO) |
| `core/workflows/marketing.py` | Marketing funnel workflow |
| `core/workflows/followup.py` | Post-visit follow-up workflow |
| `core/communications/templates_medical.py` | Medical-grade message templates |
| `channels/whatsapp_provider.py` | WhatsApp Business API client (Twilio/MessageBird/Meta) |
| `channels/whatsapp_templates.py` | Template management + Meta approval flow |
| `channels/whatsapp_flows.py` | Interactive WhatsApp Flows (booking, intake) |
| `channels/whatsapp_handoff.py` | Human handoff with context payloads |
| `admin/appointments.py` | Appointment management UI |
| `admin/compliance.py` | Compliance dashboard (consent logs, audit trail) |

## 3. Architecture — Target Layout

```
api/app/
├── admin/                  # Admin panel (KEEP + reframe)
│   ├── inbox.py            # Conversation management
│   ├── appointments.py     # NEW — appointment management
│   ├── channels.py         # Reframe — WhatsApp + Widget
│   ├── connections.py      # Reframe — CRM integrations
│   ├── agents.py           # Reframe — medical agents
│   ├── settings.py         # Workspace settings
│   ├── account.py          # Account + API keys
│   ├── compliance.py       # NEW — compliance dashboard
│   ├── logs.py             # Activity log
│   └── knowledge.py        # Knowledge base
├── auth/                   # Auth (KEEP + minor additions)
│   ├── deps.py
│   ├── jwthandler.py
│   └── routes.py
├── core/
│   ├── ai/                 # LLM (KEEP — retrain for medical)
│   │   ├── generator.py
│   │   ├── intent_classifier.py  # Medical intents
│   │   └── triage.py             # NEW — patient triage
│   ├── booking/            # NEW — appointment engine
│   │   ├── scheduler.py
│   │   ├── calendar_sync.py
│   │   ├── reminders.py
│   │   └── slot_manager.py
│   ├── communications/     # KEEP + reframe
│   │   ├── delivery.py     # WhatsApp delivery
│   │   ├── deduplication.py
│   │   ├── templates.py    # Medical templates
│   │   └── webhook_sender.py
│   ├── compliance/         # NEW
│   │   ├── consent.py
│   │   ├── phi_minimization.py
│   │   ├── audit.py
│   │   └── retention.py
│   ├── workflows/          # REFRAME — medical workflows
│   │   ├── registry.py     # Keep
│   │   ├── runtime.py      # Keep
│   │   ├── transitions.py  # Keep
│   │   ├── guards.py       # Keep
│   │   ├── appointment.py  # NEW
│   │   ├── marketing.py    # NEW
│   │   ├── followup.py     # NEW
│   │   └── scheduler.py    # Keep
│   ├── timeline/           # Keep — audit trail
│   │   ├── recorder.py
│   │   └── queries.py
│   └── memory.py           # Keep
├── channels/
│   ├── widget.py           # Keep — reframe for clinics
│   ├── whatsapp.py         # REWRITE — full BSP connector
│   ├── whatsapp_provider.py # NEW — BSP abstraction
│   ├── whatsapp_templates.py # NEW — Meta template manager
│   ├── whatsapp_flows.py   # NEW — interactive flows
│   ├── whatsapp_handoff.py # NEW — human handoff
│   └── registry.py         # Keep
├── integrations/
│   ├── credentials.py      # Keep — CRM credential management
│   ├── crm/                # NEW
│   │   ├── base.py         # Abstract connector
│   │   ├── zoho.py         # Zoho adapter
│   │   ├── hubspot.py      # HubSpot adapter
│   │   ├── salesforce.py   # Salesforce adapter
│   │   └── custom_api.py   # Custom REST API adapter
│   └── webhooks.py         # REWRITE — CRM webhooks
├── knowledge/
│   ├── __init__.py          # Keep
│   ├── catalog.py           # REFRAME — procedures/services catalog
│   └── medical_terms.py     # NEW — medical terminology
├── rag/                    # Keep — for medical docs
├── shared/                 # Keep all
│   ├── idempotency.py
│   ├── inbox_writer.py
│   ├── locks.py
│   └── queue.py
├── templates/              # REFRAME terminology
│   ├── base.html
│   ├── login.html
│   ├── landing.html
│   ├── inbox.html
│   ├── agents.html
│   ├── appointments.html   # NEW
│   ├── channels.html
│   ├── connections.html
│   ├── compliance.html     # NEW
│   ├── knowledge.html
│   ├── settings.html
│   ├── account.html
│   ├── privacy.html
│   ├── terms.html
│   └── gdpr_notice.html    # NEW
├── main.py                 # Update router includes
├── models.py               # Strip e-commerce, add medical
├── schemas.py              # Strip e-commerce, add medical
├── config.py               # Strip Shopify, add CRM + compliance
└── routes_chat.py          # Keep — chat endpoint
```

## 4. CRM Integration Strategy

### Target CRM Ecosystem

| CRM | Segment | BAA Available | PHI OK | Priority |
|-----|---------|--------------|--------|----------|
| **Zoho CRM** | SMB clinics ($14/user/mo) | Yes (paid plans) | Yes | P0 |
| **HubSpot** | Marketing/non-clinical | Enterprise only | No (unless Enterprise) | P1 |
| **Salesforce Health Cloud** | Enterprise hospitals ($325/user/mo) | Yes | Yes | P1 |
| **Pipedrive** | Elective/cosmetic ($14/user/mo) | No | No | P2 |
| **Freshsales** | Growing practices ($9/user/mo) | Yes (Pro+) | Yes | P2 |
| **Custom API** | Any clinic with proprietary CRM | N/A | N/A | P0 |

### Connector Architecture

```
                  ┌─────────────────┐
                  │  CRM Connector  │ (abstract base)
                  │  (base.py)      │
                  └────────┬────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
   ┌────────────┐   ┌────────────┐   ┌──────────────┐
   │ ZohoAdapter│   │HubSpotAdapt│   │SalesforceAdapt│
   │  (BAA ✓)   │   │ (no PHI)   │   │  (BAA ✓)     │
   └────────────┘   └────────────┘   └──────────────┘
          │                │                │
          ▼                ▼                ▼
   ┌────────────┐   ┌────────────┐   ┌──────────────┐
   │ Zoho CRM   │   │ HubSpot    │   │ Salesforce   │
   │ API        │   │ API        │   │ Health Cloud │
   └────────────┘   └────────────┘   └──────────────┘
```

Each adapter implements:
- `get_patient(patient_id)` → Patient dict
- `find_patient(email, phone)` → Patient dict | None
- `create_patient(data)` → Patient dict
- `create_appointment(patient_id, data)` → Appointment dict
- `update_appointment(appt_id, data)` → Appointment dict
- `cancel_appointment(appt_id)` → bool
- `search_available_slots(doctor_id, date)` → List[Slot]
- `get_patient_appointments(patient_id)` → List[Appointment]

## 5. WhatsApp Channel Architecture

### Message Flow
```
Patient → WhatsApp → [WhatsApp Business API / BSP]
                         ↓
                    [Webhook Receiver]
                         ↓
                    [Intent Classifier] ──→ Appointment booking?
                         ↓                    ↓ Yes → [Booking Workflow]
                    [Conversation State]       ↓
                         ↓                    ↓ No  → [Marketing/Sales/Faq]
                    [AI Response Generator]
                         ↓
                    [Template Manager] ←── Meta Template Approval
                         ↓
                    [Message Delivery] ←── Rate Limiter
                         ↓
                    [Patient ← WhatsApp]
```

### BSP (Business Solution Provider) Options

| Provider | BAA Available | HIPAA-Eligible | Notes |
|----------|--------------|----------------|-------|
| **Twilio** | Yes | Yes (with BAA signed) | Best for HIPAA — signed BAA available |
| **MessageBird** | On request | Conditional | EU-focused, GDPR-friendly |
| **Meta Cloud API** | No | No | Direct Meta — no BAA, use via BSP |
| **360dialog** | On request | Conditional | Good for EU clinics |
| **Gupshup** | On request | Conditional | Strong in emerging markets |

**Recommendation:** Twilio as primary BSP for HIPAA-eligible US clinics. 360dialog/MessageBird for EU clinics (GDPR-friendly data residency).

### Critical WhatsApp + HIPAA Pattern
1. **Keep PHI out of WhatsApp messages** — use generic templates with secure links
2. **Template messages only** for outbound — Meta pre-approves, no freeform PHI
3. **Session messages** (24h window) — patient-initiated, limited scope
4. **Secure portal links** — all clinical content behind authenticated portal
5. **Consent capture** — explicit opt-in recorded with timestamp + message ID
6. **Audit logging** — every message logged with content hash (not raw PHI)

## 6. Compliance Architecture

### GDPR (EU Clinics)
| Requirement | Implementation |
|-------------|---------------|
| Lawful basis (Art 6) | Legitimate interest for reminders; consent for marketing |
| Special category (Art 9) | Explicit consent for health data processing |
| Consent management | Capture, store, refresh annually, instant revocation |
| Data minimization | No PHI in WhatsApp — tokenized portal links |
| Retention limits | Configurable per data type (default 3 years) |
| Right to erasure | Delete patient data API + cascade through CRM |
| DPA with subprocessors | Signed with Twilio/BSP + hosting provider |
| Records of processing (Art 30) | Maintained automatically in compliance module |

### HIPAA (US Clinics)
| Requirement | Implementation |
|-------------|---------------|
| BAA with vendors | Signed with Twilio (BSP), hosting provider, CRM |
| Minimum necessary | Generic appointment messages — no diagnosis, no details |
| Encryption (TLS + AES-256) | All data in transit and at rest |
| Access controls | RBAC in admin panel + unique user IDs |
| Audit logs | Immutable message audit log with timestamps |
| Patient consent | Written consent for electronic communications |
| Breach notification | Automated incident detection + 60-day notification SLA |
| Offboarding/revocation | Immediate token + session revocation |

### WhatsApp-Specific Compliance for Healthcare
```text
NO PHI in WhatsApp messages → Generic reminders only
YES → "Your appointment is tomorrow at 10:00 AM at City Clinic"
NO  → "Your oncology follow-up with Dr. Smith for chemotherapy planning"
YES → "Your lab results are ready. Click here to view securely: [tokenized link]"
NO  → "Your HbA1c is 7.2 — higher than last month's 6.8"
```

## 7. Workflow Agents — Medical Domain

### Agent: Appointment Manager (replaces WISMO)
```
States:
  AWAITING_INTENT → CLASSIFYING → CHECKING_SCHEDULE → OFFERING_SLOTS
  → CONFIRMING → BOOKED | RESCHEDULING | CANCELLING
  → REMINDER_SENT → ARRIVED | NO_SHOW | COMPLETED

Triggers:
  - Patient messages "I need to see a doctor"
  - Patient messages "Cancel my appointment"
  - Pre-scheduled reminder (T-24h, T-2h)
  - Post-visit follow-up (D+1, D+7)
```

### Agent: Marketing Funnel (NEW)
```
States:
  LEAD_CAPTURED → QUALIFYING → NURTURING → APPOINTMENT_BOOKED
  → FOLLOW_UP → CONVERTED | LOST

Channels:
  - Promotional campaigns (opt-in only)
  - Seasonal reminders (flu shots, screenings)
  - Recall campaigns (annual checkup)
  - Post-treatment review requests
```

### Agent: Patient Follow-up (NEW)
```
States:
  VISIT_COMPLETED → DAY_1_CHECK → DAY_7_CHECK → DAY_30_CHECK
  → MEDICATION_ADHERENCE → SATISFACTION_SURVEY → CLOSED

Functions:
  - Post-procedure wellness checks
  - Medication adherence ping
  - Satisfaction (NPS/CSAT) collection
  - Referral request
```

## 8. Agent Architecture — LLM Boundary

```
┌─────────────────────────────────────────────┐
│               LLM (Temperature: 0.1-0.3)     │
│  MAY: classify intent, summarize, generate   │
│        empathetic response, detect sentiment │
│  NEVER: book appointments, change state,     │
│         authorize actions, schedule retries  │
└──────────────────┬──────────────────────────┘
                   │ returns structured intent
                   ▼
┌─────────────────────────────────────────────┐
│          Deterministic Workflow Engine       │
│  OWNS: slot management, booking, reminders,  │
│        all operational actions, state machine │
│  Fallback: static templates, default flows   │
└─────────────────────────────────────────────┘
```

## 9. Models — New Schema

### New Medical Models to ADD
```python
class Patient(Base):
    __tablename__ = "patients"
    id: UUID | None = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: UUID = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    external_id: str | None        # CRM patient ID
    first_name: str
    last_name: str
    email: str | None
    phone: str
    date_of_birth: date | None
    gender: str | None
    consent_status: str | None     # pending | granted | revoked | expired
    consent_timestamp: datetime | None
    consent_channel: str | None    # whatsapp | widget | web
    gdpr_data_retention: str | None # retention policy applied
    metadata: dict | None = Column(JSONB, default=dict)  # CRM-specific fields
    created_at: datetime = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: datetime = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Appointment(Base):
    __tablename__ = "appointments"
    id: UUID | None = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: UUID = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    patient_id: UUID = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True)
    external_id: str | None        # CRM appointment ID
    provider_name: str
    provider_specialty: str | None
    department: str | None
    start_time: datetime
    end_time: datetime
    status: str                     # scheduled | confirmed | arrived | in_progress
                                    # completed | cancelled | no_show | rescheduled
    reason: str | None              # reason for visit
    notes: str | None
    source: str                     # whatsapp | widget | crm | web
    slot_token: str | None          # optimistic locking
    reminder_sent_24h: bool = False
    reminder_sent_2h: bool = False
    consent_id: UUID | None = Column(UUID(as_uuid=True), ForeignKey("consent_logs.id"))
    created_at: datetime = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: datetime = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ConsentLog(Base):
    __tablename__ = "consent_logs"
    id: UUID | None = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = ...
    patient_id = ...
    type: str                       # marketing | appointment | phi_whatsapp | data_processing
    status: str                     # granted | revoked | expired
    channel: str                    # whatsapp | widget | web | admin
    consent_text: str               # exact text patient agreed to
    ip_address: str | None
    user_agent: str | None
    granted_at: datetime
    revoked_at: datetime | None
    expires_at: datetime | None

class Provider(Base):
    __tablename__ = "providers"
    id: UUID | None = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = ...
    external_id: str | None
    name: str
    specialty: str | None
    email: str | None
    phone: str | None
    schedule: dict | None = Column(JSONB, default=dict)  # availability rules
    created_at...
    updated_at...

class CrmConnection(Base):
    __tablename__ = "crm_connections"
    id: UUID | None = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = ...
    provider: str                   # zoho | hubspot | salesforce | custom_api
    config: dict = Column(JSONB)    # encrypted credentials, endpoints, mappings
    status: str                     # connected | disconnected | error
    last_sync_at: datetime | None
    webhook_secret: str | None
    created_at...
    updated_at...

class AuditLog(Base):  # Extended for compliance
    __tablename__ = "audit_logs"
    id: UUID | None = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = ...
    patient_id: UUID | None
    actor_type: str                 # patient | staff | system | whatsapp
    actor_id: str | None
    action: str                     # message_sent | appointment_booked | consent_granted
                                    # phi_accessed | data_exported | data_deleted
    resource_type: str
    resource_id: str | None
    details: dict = Column(JSONB, default=dict)  # NOT raw PHI — references/tokens
    ip_address: str | None
    timestamp: datetime = Column(DateTime, default=datetime.utcnow, nullable=False)
    retention_until: datetime | None
```

### Fields to REMOVE from existing models
| Model | Field | Reason |
|-------|-------|--------|
| `Customer` | `shopify_customer_id` | E-commerce |
| `ChannelConfig` | Email-specific fields | Email channel removed |
| Various | `product_id`, `subscription_id` | E-commerce |
| `NativeConnector` | Shopify-specific meta fields | CRMs replace |

## 10. Template/UI Changes Needed

### Pages to REWRITE
| Template | Current | Target |
|----------|---------|--------|
| `landing.html` | "AI customer support for e-commerce" | "AI patient communication for clinics" |
| `agents.html` | WISMO (order tracking) | Appointment Manager + Marketing + Follow-up |
| `channels.html` | Widget + Email + WhatsApp (stub) | WhatsApp (full) + Widget |
| `connections.html` | Shopify integration | CRM integration (Zoho/HubSpot/Salesforce) |
| `knowledge.html` | Product catalog (SKU/price/stock) | Services catalog + medical docs |

### Pages to ADD
| Template | Description |
|----------|-------------|
| `appointments.html` | Calendar view, slot management, booking overview |
| `compliance.html` | Consent logs, audit trail viewer, retention policy config |
| `gdpr_notice.html` | GDPR-compliant privacy notice for EU patients |

### Pages to REMOVE
| Template | Reason |
|----------|--------|
| None needed — `settings.html` can become legacy redirect |

## 11. Cleanup Implementation Plan

### Phase 1: Foundation (Days 1-3)
1. Remove Shopify — delete `integrations/shopify/`, `integrations_routes.py`
2. Strip e-commerce fields from `models.py`
3. Remove `core/commerce/`
4. Remove `channels/base.py`, `channels/rest.py`
5. Strip Shopify config from `config.py`
6. Update `main.py` — remove Shopify webhooks, integrations_routes
7. Verify `python -c "from app.main import app"` passes

### Phase 2: Compliance Layer (Days 4-7)
1. Create `core/compliance/` — consent, PHI minimization, audit, retention
2. Add new models — `Patient`, `Appointment`, `ConsentLog`, `Provider`, `CrmConnection`
3. Run Alembic migration
4. Create `AuditLog` extended model
5. Implement GDPR consent capture flow

### Phase 3: CRM Integration (Days 8-12)
1. Create `integrations/crm/base.py` — abstract connector
2. Create `integrations/crm/zoho.py` — first adapter
3. Create `integrations/crm/hubspot.py` — second adapter
4. Create webhook receiver for CRM events
5. Update admin `connections` page for CRM config
6. Update `integrations/credentials.py` for CRM providers

### Phase 4: WhatsApp Channel (Days 13-18)
1. Rewrite `channels/whatsapp.py` — full BSP integration
2. Implement Twilio BSP connector (BAA-compatible)
3. Implement Meta template management
4. Create `channels/whatsapp_flows.py` — interactive flows
5. Create `channels/whatsapp_handoff.py` — human handoff
6. Wire webhook receiver for inbound WhatsApp messages
7. Update `channels.html` — full WhatsApp configuration UI

### Phase 5: Workflows — Appointment Booking (Days 19-23)
1. Create `core/booking/` — scheduler, slot manager, calendar_sync
2. Create `core/workflows/appointment.py` — state machine
3. Create `core/ai/triage.py` — medical intent classification
4. Update `core/ai/intent_classifier.py` — medical intents
5. Train/configure prompts for medical domain
6. Create `admin/appointments.py` — appointment management API

### Phase 6: Marketing & Follow-up Agents (Days 24-27)
1. Create `core/workflows/marketing.py` — campaign funnel
2. Create `core/workflows/followup.py` — post-visit care
3. Wire campaign triggers (scheduled, event-based)
4. Analytics tracking

### Phase 7: UI Reframe (Days 28-30)
1. Rewrite `landing.html` — medical clinic marketing
2. Update `agents.html` — show new medical agents
3. Update `connections.html` — CRM config UI
4. Update `knowledge.html` — medical services catalog
5. Create `compliance.html` — compliance dashboard
6. Create `appointments.html` — calendar and booking UI
7. Update all terminology in templates

### Phase 8: Testing & Polish (Days 31-33)
1. Integration tests — CRM connectors
2. Integration tests — WhatsApp channel
3. Compliance audit test — data retention, consent flow
4. End-to-end test — full booking flow
5. Update AGENTS.md with new architecture rules
6. Remove deprecated dead code (workers, execution, policies, escalations)

## 12. Dependency Direction (Updated)

```
core/ → models, config, db           (ALLOWED)
core/ → shared/                       (ALLOWED — locks, idempotency, inbox)
core/compliance → core/timeline       (ALLOWED — audit)
core/booking → shared/locks           (ALLOWED — optimistic locking)
core/workflows → core/booking         (ALLOWED)
core/workflows → core/communications  (ALLOWED)
core/workflows → core/compliance      (ALLOWED — consent checks)
integrations/crm → core/compliance    (ALLOWED — PHI minimization)
integrations/crm → models, config     (ALLOWED)
channels/ → core/ai, core/booking     (ALLOWED)
channels/ → core/compliance           (ALLOWED — consent)
admin/ → core/, models, db            (ALLOWED)
auth/ → models, config, db            (ALLOWED)

FORBIDDEN:
core/ → admin/, auth/, channels/      (NEVER — core is engine, not UI)
admin/ → channels/ (except via core/)
integrations/ → admin/
```

## 13. Key Risks & Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| WhatsApp + HIPAA conflict (Meta won't sign BAA) | Medium | Use Twilio as BSP (signed BAA); keep PHI out of WhatsApp messages |
| CRM API differences between providers | High | Well-designed abstract base + comprehensive adapter tests |
| Medical intent classification accuracy | Medium | LLM with temperature 0.1 + deterministic fallback + human handoff |
| GDPR right to erasure cascade | Medium | Soft-delete pattern + cascade through CRM adapters |
| Appointment slot race conditions | Low | Optimistic locking with `slot_token` + 2-phase commit |
| Template approval delays (Meta) | Medium | Submit templates early; fallback to session messaging |
| Data residency requirements (EU vs US) | Medium | Configurable storage region at tenant level |
