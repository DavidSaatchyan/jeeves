# UX/UI Implementation Plan

Based on `v2 requirements/8 UX UI.md`.

---

## Navigation Architecture

### Required (per 8 UX UI)
```
Overview
Workflows
Customers
Inbox
Approvals
Knowledge
Analytics
Billing
Settings
```

### Current
```
Overview → Dashboard
Connect → Integrations
Channels
Workflows → Active, Escalations, Policies
Analytics
Activity → Timeline
Developer → API, Knowledge, Billing
```

### Changes needed
- `Connect` + `Channels` → move under `Settings > Integrations` / `Settings > Channels`
- `Activity > Timeline` → merge into Overview or remove
- `Developer > API` → move under `Settings > Security`
- `Developer > Knowledge` → promote to top-level
- `Developer > Billing` → promote to top-level
- Add `Customers`, `Inbox`, `Approvals`, `Settings`

---

## Phase 1 — Backend Models & API (архитектурные изменения)

### 1.1 ApprovalRequest model + API

**Model fields:**
```
id                UUID PK
tenant_id         FK → tenants
workflow_id       FK → workflows
customer_id       FK → customers
action_type       String   (discount, refund, credit, escalate)
action_value      JSONB    (amount, reason, etc.)
reason            Text     (AI-generated reason for the action)
expected_outcome  Text
risk_level        String   (low, medium, high)
ai_confidence     Integer  (0-100)
status            String   (PENDING, APPROVED, REJECTED, ESCALATED, ALWAYS_ALLOW)
reviewed_by       Text     (admin who acted)
reviewed_at       DateTime
policy_reference  Text     (which policy rule triggered this)
simulation_result JSONB    (predicted outcome if approved)
created_at        DateTime
updated_at        DateTime
```

**API endpoints:**
```
GET    /admin/api/approvals              — queue with filters (status, risk)
GET    /admin/api/approvals/{id}         — detail with full AI reasoning
POST   /admin/api/approvals/{id}/approve — approve once
POST   /admin/api/approvals/{id}/always  — always allow under policy
POST   /admin/api/approvals/{id}/reject  — reject
POST   /admin/api/approvals/{id}/escalate— escalate to human
```

### 1.2 Inbox/Conversation structure

No new model needed for MVP. ChatLog already supports:
- `session_id` groups messages → conversations
- `channel` distinguishes source
- `resolution` tracks escalated/resolved state
- `delivered` flag for inbox

**API endpoints to add:**
```
GET    /admin/api/inbox                  — conversation list (grouped by session_id)
GET    /admin/api/inbox/{session_id}     — full conversation thread
POST   /admin/api/inbox/{session_id}/takeover — human takeover
```

**AI Assist — endpoint:**
```
POST   /admin/api/inbox/{session_id}/suggest — generate reply draft / save offer
```

### 1.3 Customer API endpoints

**Model exists** — Customer (with risk_level, sentiment_state, frustration_score).

**API endpoints to add:**
```
GET    /admin/api/customers              — list with search + filters
GET    /admin/api/customers/{id}         — detail with subscription/order/payment history
GET    /admin/api/customers/{id}/timeline— unified operational timeline
GET    /admin/api/customers/{id}/context — AI context panel data (risk, sentiment, recommendations)
```

### 1.4 Customer risk scoring logic

**What exists:**
- WISMO risk classification (`classifier.py`)
- Payment failure classification (`classifier.py`)
- Cancellation intent classification (`classifier.py`)
- Sentiment/frustration detection (`sentiment.py`)

**What to add:**
```
core/commerce/risk.py → compute_customer_risk(customer_id) → unified risk score
  - aggregates: payment history, sentiment trends, subscription state, escalation history
  - writes to Customer.risk_level
```

### 1.5 Settings models

For MVP — minimal. No Team/Role/Permission yet.

**NotificationPreferences model:**
```
id                UUID PK
tenant_id         FK → tenants
escalation_alerts      Boolean (default true)
approval_alerts        Boolean (default true)
workflow_failure_alerts Boolean (default true)
daily_summary          Boolean (default false)
```

**Settings API:**
```
GET    /admin/api/settings
PUT    /admin/api/settings
```

### 1.6 Alembic migration
One migration for all new tables/columns.

---

## Phase 2 — Core UX Pages

### 2.1 Overview (Dashboard rewrite)

**Layout per 8 UX UI:**
```
Section 1 — AI System Status Hero
  - AI Operations Active banner
  - Active workflows count, automation success %, recovered revenue, pending approvals, escalations

Section 2 — Attention Queue
  - Cards: pending approvals, escalations, failed workflows, sync issues, policy conflicts
  - Quick actions, bulk resolve

Section 3 — Live Operations Feed
  - Real-time timeline (timestamp, workflow, customer, AI action, result, revenue impact)
  - Uses existing `/admin/api/timeline`

Section 4 — Revenue Impact
  - KPIs: recovered revenue, prevented churn, saved subscriptions, tickets avoided, automation rate

Section 5 — Workflow Health
  - Health map per workflow type
```

### 2.2 Workflows (rewrite with tabs)

**Tabs (per user feedback — tabs not cards):**
```
[ Payment Recovery | Cancellation Save | WISMO ]  ← tabs, one per workflow type
```

Each tab shows:
```
Workflow Name / Type label
Status badge
Automation level
Execution volume
Success rate
Revenue impact
Escalation rate
Last activity
```

**Workflow detail:**
```
A. Header — status, automation mode, metrics, enable/disable, last activity
B. Workflow Map — visual state machine (rendered as SVG/steps)
C. Workflow Policies — grouped controls inline:
   - Automation Boundaries (outreach, reminders, retries — approval required for discounts, refunds)
   - Retry Policy — visual retry builder (NOT raw inputs)
   - Escalation Policy — if frustration → escalate, if recovery > $300 → approval
   - Communication Policy — channels, max attempts, cooldown, quiet hours
D. Workflow Analytics — conversion, save rate, recovery rate, escalation rate, AI confidence
E. Execution Timeline — full audit trail
```

### 2.3 Customers (new)

**List page:**
```
Search bar
Columns: customer, subscription state, risk, workflow state, revenue value, escalations, sentiment
```

**Detail page:**
```
Unified timeline: orders, subscriptions, payments, messages, AI actions, escalations, approvals, retries, notes
Right panel: AI Context (customer summary, churn risk, anomalies, recommended actions)
```

### 2.4 Inbox (new)

**Layout per 8 UX UI:**
```
Left:   Conversation list (grouped by type: AI conversations, escalated, approval-needed, human takeover)
Center: Conversation thread
Right:  Operational context panel (customer profile, orders, subscription, workflow state, AI reasoning, knowledge used, suggested actions)
```

**AI Assist:**
```
Agent suggestions: reply drafts, save offers, escalation recommendation, refund reasoning
```

### 2.5 Approvals (new)

**Queue page:**
```
Each item: customer, action requested, reason, expected outcome, risk level, AI confidence, revenue impact
Actions: Approve once, Always allow, Reject, Escalate
```

**Detail view:**
```
Full AI reasoning
Policy reference
Historical context
Simulation outcome
Affected workflows
```

### 2.6 Knowledge (upgrade)

**Add:**
- AI Readiness section (WISMO readiness → High, Refund policy → Medium, etc.)
- Missing Knowledge Detection (AI identifies gaps in knowledge base)
- AI Playground — simulate WISMO / cancellation / failed payment, show AI response + confidence + sources + workflow path

### 2.7 Analytics (upgrade)

**Add sections:**
- Operations: automation rate, tickets avoided, human takeover rate, avg response time
- AI Performance: approval rate, escalation accuracy, AI confidence, policy override frequency

### 2.8 Settings (new page)

**Tabs:**
```
[ Workspace | Integrations | Channels | Security | Notifications ]
```

- Workspace: org name, team
- Integrations: current Shopify/Recharge/Stripe cards with health + sync state + capabilities
- Channels: Widget config + Email config
- Security: API keys, sessions
- Notifications: toggle escalation/approval/failure alerts, daily summary

---

## Phase 3 — Global Layout + AI UX

### 3.1 Top Context Bar
Dynamic per page: current scope, workflow context, filters, live sync status, AI health.

### 3.2 Right Context Panel (conditional)
Shows on Customers detail, Inbox conversation, Approval detail.

### 3.3 Sidebar
- Collapsible
- Escalation badge count
- Notification indicator

### 3.4 AI Explainability
Every AI action shows: what happened, why, what policy allowed it, confidence, human override options.

### 3.5 Design system alignment
- Semantic colors: blue=AI action, green=revenue, yellow=pending, red=escalation, purple=workflow
- Dense but readable
- Low-noise dark interface
- Monospace for IDs/states/events

### 3.6 UX states
All pages support: empty, loading, partial sync failure, no permissions, degraded automation, approval waiting, success, escalated.

---

## Order of implementation

```
Phase 1.1 → 1.2 → 1.3 → 1.4 → 1.5 → 1.6 (migration)
  ↓
Phase 2.1 (Overview) + 2.2 (Workflows)
  ↓
Phase 2.3 (Customers) + 2.4 (Inbox)
  ↓
Phase 2.5 (Approvals) + 2.7 (Analytics upgrade)
  ↓
Phase 2.6 (Knowledge upgrade) + 2.8 (Settings)
  ↓
Phase 3.1 → 3.2 → 3.3 → 3.4 → 3.5 → 3.6
```

Start with Phase 1.1.
