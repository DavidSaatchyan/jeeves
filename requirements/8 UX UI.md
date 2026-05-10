# UX/UI

Основа продукта:

> AI operational system for Shopify subscription brands.
> 

Не helpdesk.

Не chatbot builder.

Не integrations dashboard.

Система должна ощущаться как:

# Operational AI Control Center

---

# 1. PRODUCT UX PRINCIPLES

# 1.1 Core UX philosophy

Интерфейс должен отвечать на 5 вопросов:

```
1. Что происходит?
2. Что AI делает?
3. Что требует моего внимания?
4. Какие результаты?
5. Где границы автономии?
```

---

# 1.2 Product pillars

## A. Operational Visibility

Пользователь всегда понимает:

- текущее состояние системы;
- workflow execution;
- customer state;
- AI decisions;
- escalation state.

---

## B. Bounded Autonomy

AI никогда не ощущается black box.

Каждое действие:

- объяснимо;
- ограничено политиками;
- audit-able;
- reversible.

---

## C. Revenue-Centric UX

Продукт продает:

- recovered revenue;
- reduced support load;
- operational leverage.

Не AI ради AI.

---

## D. Human + AI Collaboration

AI:

- автоматизирует;
- предлагает;
- исполняет bounded actions.

Человек:

- утверждает;
- контролирует;
- эскалирует;
- оптимизирует.

---

# 2. GLOBAL INFORMATION ARCHITECTURE

# PRIMARY NAVIGATION

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

---

# 3. GLOBAL LAYOUT SYSTEM

# 3.1 Shell Structure

```
Left Sidebar
Top Context Bar
Main Workspace
Right Context Panel (conditional)
```

---

# 3.2 Sidebar behavior

Sidebar:

- collapsible;
- persistent;
- optimized for dense operations.

Contains:

- navigation;
- system status;
- tenant switcher;
- notifications;
- escalation badge.

---

# 3.3 Top Context Bar

Dynamic per page.

Shows:

- current scope;
- workflow context;
- filters;
- live sync status;
- AI system health.

---

# 4. OVERVIEW PAGE

# Purpose

Mission control for AI operations.

---

# Layout

## SECTION 1 — AI SYSTEM STATUS HERO

```
AI Operations Active

3 workflows active
92% automation success
$14,230 recovered this month
4 approvals pending
1 escalation waiting
```

---

## SECTION 2 — ATTENTION QUEUE

Priority operational queue.

Cards:

- pending approvals;
- escalations;
- failed workflows;
- sync issues;
- policy conflicts.

Must support:

- quick actions;
- keyboard navigation;
- bulk resolve.

---

## SECTION 3 — LIVE OPERATIONS FEED

Real-time operational timeline.

Each event contains:

```
Timestamp
Workflow
Customer
AI action
Result
Revenue impact
Approval state
```

Example:

```
03:14
Payment Recovery
AI sent payment update email

03:31
Customer updated payment method

03:35
Retry successful
+$89 recovered
```

---

## SECTION 4 — REVENUE IMPACT

Primary KPI layer.

Metrics:

- recovered revenue;
- prevented churn;
- saved subscriptions;
- tickets avoided;
- automation rate.

---

## SECTION 5 — WORKFLOW HEALTH

Operational health map.

```
Recovery → healthy
WISMO → degraded
Cancellation Save → approval bottleneck
```

---

# 5. WORKFLOWS

# Purpose

Central automation management layer.

---

# Workflow list page

Workflows shown as operational systems.

Cards:

```
Workflow Name
Status
Automation level
Execution volume
Success rate
Revenue impact
Escalation rate
Last activity
```

---

# Supported MVP workflows

```
Payment Recovery
Cancellation Save
WISMO
```

---

# Workflow detail page

# Structure

## A. Workflow Header

Contains:

- status;
- automation mode;
- execution metrics;
- enable/disable;
- last deployment.

---

## B. Workflow Map

Visual state machine.

Example:

```
Failed payment
↓
Detect
↓
AI outreach
↓
Wait response
↓
Retry payment
↓
Recovered
OR
Escalate
```

Must support:

- step inspection;
- execution logs;
- latency visibility;
- policy boundaries.

---

## C. Workflow Policies

Grouped operational controls.

---

### Automation Boundaries

```
AI can:
✓ outreach
✓ reminders
✓ retries

Approval required:
✓ discounts
✓ refunds
✓ credits
```

---

### Retry Policy

Visual retry builder.

NOT raw input fields.

```
Retry 1 → 5 min
Retry 2 → 1 hour
Retry 3 → 24 hours
```

---

### Escalation Policy

```
If frustration detected:
→ escalate

If recovery > $300:
→ approval required
```

---

### Communication Policy

```
Allowed channels:
✓ Email
✓ Widget

Max attempts: 3
Cooldown: 24h
Quiet hours enabled
```

---

## D. Workflow Analytics

Workflow-specific:

- conversion;
- save rate;
- recovery rate;
- escalation rate;
- AI confidence;
- approval frequency.

---

## E. Execution Timeline

Full operational audit trail.

---

# 6. CUSTOMERS

# Purpose

Unified operational customer memory.

---

# Customer list

Searchable operational CRM-lite.

Columns:

- customer;
- subscription state;
- risk;
- workflow state;
- revenue value;
- escalations;
- sentiment.

---

# Customer detail page

Unified timeline:

```
Orders
Subscriptions
Payments
Messages
AI actions
Escalations
Approvals
Retries
Notes
```

---

# AI Context Panel

Displays:

- customer summary;
- churn risk;
- operational anomalies;
- recommended actions.

---

# 7. INBOX

# Purpose

Human + AI collaboration layer.

---

# Inbox types

```
AI conversations
Escalated conversations
Approval-needed conversations
Human takeover
```

---

# Conversation layout

## Left:

Conversation list

## Center:

Conversation thread

## Right:

Operational context panel

---

# Right panel includes

```
Customer profile
Orders
Subscription
Workflow state
AI reasoning
Knowledge used
Suggested actions
```

---

# AI Assist Layer

Agent suggestions:

- reply drafts;
- save offers;
- escalation recommendation;
- refund reasoning.

---

# 8. APPROVALS

# Purpose

Trust architecture layer.

---

# Approval queue

Each item contains:

```
Customer
Requested action
Reason
Expected outcome
Risk level
AI confidence
Revenue impact
```

---

# Actions

```
Approve once
Always allow under policy
Reject
Escalate
```

---

# Approval detail view

Shows:

- full AI reasoning;
- policy reference;
- historical context;
- simulation outcome;
- affected workflows.

---

# 9. KNOWLEDGE

# Purpose

Operational AI memory system.

---

# Knowledge overview

```
Coverage
Readiness
Missing knowledge
Sync health
Source quality
```

---

# Knowledge sources

Supported:

- PDF;
- website sync;
- FAQ;
- SOPs;
- policy docs;
- Shopify policies;
- macros/templates.

---

# AI Readiness

```
WISMO readiness → High
Refund policy confidence → Medium
Retention policy coverage → Low
```

---

# Missing Knowledge Detection

AI identifies gaps.

Example:

```
Missing:
- damaged shipment policy
- prepaid annual cancellation handling
```

---

# AI Playground

Testing environment.

User can simulate:

- WISMO;
- cancellation request;
- failed payment.

Displays:

- AI response;
- confidence;
- knowledge sources used;
- workflow path triggered.

---

# 10. ANALYTICS

# Purpose

Operational ROI visibility.

---

# Sections

## Revenue

```
Recovered revenue
Recovered MRR
Saved subscriptions
Prevented churn
```

---

## Operations

```
Automation rate
Tickets avoided
Human takeover rate
Avg response time
```

---

## AI Performance

```
Approval rate
Escalation accuracy
AI confidence
Policy override frequency
```

---

# 11. BILLING

# Purpose

Commercial control surface.

---

# Billing overview

```
Current plan
Usage
Workflow volume
Seats
AI consumption
Overages
Next invoice
```

---

# Pricing dimensions

Possible usage metrics:

- active workflows;
- conversations;
- AI actions;
- recovered revenue share;
- seats.

---

# Billing sections

## Usage

Operational consumption.

```
Recovery workflows used
Messages processed
AI actions executed
Approvals consumed
```

---

## Plan Management

```
Upgrade
Downgrade
Seat management
Usage limits
```

---

## Invoices

```
Invoices
Payment method
Billing history
Tax info
```

---

# 12. SETTINGS

# Purpose

System-level configuration.

NOT operational management.

---

# Structure

## Workspace

```
Organization
Team
Roles
Permissions
```

---

## Integrations

```
Shopify
Recharge
Stripe
Klaviyo
Slack
```

Each integration includes:

- health;
- sync state;
- permissions;
- capabilities enabled.

---

## Channels

```
Website widget
Email
WhatsApp (future)
SMS (future)
```

---

## Security

```
SSO
Audit logs
API keys
Sessions
```

---

## Notifications

```
Escalations
Approval alerts
Workflow failures
Daily summaries
```

---

# 13. CHANNEL EXPERIENCE

# Website Widget

Must include:

## Live preview

Desktop + mobile.

---

## Brand customization

```
Accent color
Greeting
Tone
Position
Avatar
```

---

## Behavior settings

```
Require email
Escalation behavior
Fallback mode
Business hours
```

---

## Installation

Simple copy-paste snippet.

---

# 14. INTEGRATION UX

# Integration cards

Must display:

```
Connection status
Last sync
Capabilities enabled
Data health
API errors
```

---

# Post-connection visibility

```
Payment Recovery → enabled
WISMO → enabled
Cancellation Save → partial
```

---

# 15. DESIGN SYSTEM

# Visual direction

References:

- Linear
- Stripe Radar
- Vercel
- Retool
- Cursor
- Palantir-lite

---

# Principles

## Dense but readable

Professional operations UI.

---

## Low-noise dark interface

Minimal saturation.

---

## Semantic color system

```
Blue → AI action
Green → recovered revenue
Yellow → pending approval
Red → escalation/failure
Purple → workflow state
Gray → inactive/system
```

---

# Typography

Strong hierarchy.

Use:

- compact operational text;
- monospace for IDs/states/events.

---

# Motion

Subtle operational motion only:

- state transitions;
- workflow progression;
- live events.

No decorative animations.

---

# 16. CORE UX STATES

Every page must support:

```
Empty
Loading
Partial sync failure
No permissions
Degraded automation
Approval waiting
Success
Escalated
```

---

# 17. AI UX REQUIREMENTS

# Explainability everywhere

Every AI action must show:

```
What happened
Why it happened
What policy allowed it
Confidence
Human override options
```

---

# AI confidence system

```
High
Medium
Low
Needs review
```

---

# Human override

Always available.

---

# 18. SYSTEM FEEL

The system should feel:

```
Operational
Trustworthy
Deterministic
Intelligent
Controlled
High-signal
Mission-critical
```

NOT:

- playful;
- chatbot-first;
- consumer AI;
- generic SaaS admin.

---

# 19. FINAL PRODUCT POSITIONING THROUGH UX

The UX must communicate:

> “Jeeves runs operational customer workflows reliably with AI — while keeping humans fully in control.”
> 

That is the entire interface philosophy.