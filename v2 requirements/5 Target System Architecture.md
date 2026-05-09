# Target System Architecture v2

Основа:

- Product Overview (current state)
- Definition Doc (target MVP)
- Workflow Requirements

---

# 1. Architectural North Star

# CURRENT

```
LLM-centric support platform
```

---

# TARGET

```
Deterministic Operational Workflow System
with bounded AI assistance
```

---

# Core principle

AI becomes:

```
communication + classification layer
```

NOT:

```
execution authority
```

This is explicitly required by Requirements:

> LLM NEVER directly executes operational actions.
> 

---

# 2. Architectural Style

Target architecture becomes:

```
event-driven modular monolith
```

NOT:

- microservices;
- chatbot orchestrator;
- AI-agent runtime.

---

# Why modular monolith

Perfect for MVP because:

- fast iteration;
- AI/vibecoding friendly;
- shared DB easier;
- lower operational complexity;
- transactional consistency easier;
- easier deterministic guarantees.

---

# 3. High-Level System Shape

# TARGET SYSTEM

```
Channels
    ↓
Ingress Layer
    ↓
Event System
    ↓
Workflow Engine
    ↓
Policy Engine
    ↓
Execution Engine
    ↓
Operational Integrations
    ↓
Audit + Timeline + Escalation
```

AI sits beside workflows:

```
AI = bounded assistant layer
```

---

# 4. Bounded Contexts

This is the MOST important section.

Current system lacks bounded contexts.

Everything is mixed inside:

- agent;
- CRM;
- tools;
- channels.

---

# TARGET BOUNDED CONTEXTS

---

# A. Identity & Tenant Context

### Responsibilities

- auth;
- tenants;
- RBAC;
- API keys;
- sessions;
- billing account.

---

### Reuse

Mostly existing auth system.

---

# B. Channel & Communication Context

### Responsibilities

- widget;
- email;
- customer conversations;
- outbound messaging;
- message delivery tracking.

---

### Important change

Current:

```
chat-first
```

Target:

```
workflow-driven communication
```

---

### Internal modules

```
conversation_manager
email_dispatcher
message_templates
delivery_tracking
customer_identity_resolution
```

---

# C. Event Ingestion Context

# NEW CORE CONTEXT

---

### Responsibilities

Convert external signals into canonical events.

---

### Sources

- Stripe webhooks;
- Recharge events;
- Shopify events;
- customer messages;
- shipment updates.

---

### Example canonical events

```
payment_failed
payment_recovered
subscription_cancel_requested
shipment_delayed
tracking_updated
customer_frustrated
```

---

### Internal modules

```
stripe_ingestor
recharge_ingestor
shopify_ingestor
tracking_ingestor
message_ingestor
event_normalizer
event_deduplicator
```

---

# D. Workflow Engine Context

# THE TRUE HEART OF THE PRODUCT

---

### Responsibilities

- workflow lifecycle;
- state transitions;
- orchestration;
- retries;
- workflow locking;
- expiration;
- scheduling.

---

# Important

This replaces:

- agent.run;
- tool loop orchestration.

---

### Internal modules

```
workflow_runtime
workflow_registry
state_machine_engine
transition_validator
workflow_scheduler
workflow_lock_manager
```

---

### Core workflows

MVP:

```
failed_payment_recovery
cancellation_save
wismo
```

---

# E. Policy Engine Context

# NEW CORE CONTEXT

---

### Responsibilities

Merchant governance.

---

### Controls

- retry limits;
- allowed actions;
- escalation thresholds;
- communication cadence;
- approval requirements.

---

### Important principle

Policies override AI.

Required by Requirements:

> Policy engine overrides AI-generated suggestions.
> 

---

### Internal modules

```
policy_evaluator
retry_policy_engine
approval_rules
communication_policy_engine
escalation_policy_engine
```

---

# F. Operational Execution Context

# EXTREMELY IMPORTANT

---

### Responsibilities

Deterministic operational actions.

---

### Actions

- retry payment;
- pause subscription;
- skip shipment;
- send email;
- create escalation.

---

### Important principle

This is NOT:

```
generic AI tools
```

This IS:

```
strict operational execution layer
```

---

### Internal modules

```
action_dispatcher
idempotency_manager
execution_guards
execution_audit
retry_coordinator
```

---

# G. Commerce Domain Context

# CRITICAL NEW CONTEXT

---

### Responsibilities

Canonical operational model.

---

### Canonical entities

```
Customer
Subscription
Invoice
PaymentFailure
Shipment
TrackingState
```

---

### Important principle

NO generic CRM abstraction anymore.

---

### Internal modules

```
customer_service
subscription_service
billing_service
shipment_service
tracking_normalizer
```

---

# H. Escalation & Human Ops Context

# NEW CORE CONTEXT

---

### Responsibilities

- human handoff;
- workflow pause;
- operator ownership;
- SLA tracking;
- escalation resolution.

---

### Internal modules

```
escalation_manager
human_handoff
sla_tracker
operator_queue
workflow_pause_handler
```

---

# I. Audit & Timeline Context

# TRUST LAYER

---

### Responsibilities

- event timeline;
- state transition logs;
- action history;
- replay;
- debugging.

---

### Important

This becomes:

```
core trust primitive
```

NOT just logs.

---

### Internal modules

```
timeline_store
audit_recorder
workflow_replay
event_trace
decision_trace
```

---

# J. AI Assistance Context

# IMPORTANT REPOSITIONING

---

### Responsibilities

ONLY:

- communication generation;
- classification;
- summarization;
- sentiment detection.

---

### AI forbidden from:

- state transitions;
- execution authorization;
- retry decisions;
- workflow control.

---

### Internal modules

```
intent_classifier
failure_classifier
sentiment_detector
message_generator
summary_generator
```

---

# K. Knowledge Context

# SECONDARY CONTEXT

---

### Responsibilities

Lightweight support continuity.

---

### Allowed usage

- FAQ;
- refund policy;
- shipping policy;
- operational explanations.

---

### Important

Knowledge system is:

```
adjacent support layer
```

NOT:

```
product core
```

---

# 5. Core Execution Flow

# FAILED PAYMENT FLOW

---

## Step 1

Stripe/ReCharge webhook arrives.

↓

## Step 2

Event Ingestion creates:

```
payment_failed
```

↓

## Step 3

Workflow Engine:

- creates workflow;
- acquires lock;
- validates eligibility.

↓

## Step 4

Policy Engine:

- validates retry rules;
- validates cadence;
- validates escalation thresholds.

↓

## Step 5

Execution Engine:

- schedules retry;
- sends communication;
- records idempotency keys.

↓

## Step 6

AI Layer:

- generates customer-friendly email/message.

↓

## Step 7

Audit Timeline records:

- event;
- transition;
- decisions;
- actions.

↓

## Step 8

Workflow waits for:

- payment success;
- customer action;
- timeout;
- escalation.

---

# 6. Core Architectural Principles

---

# PRINCIPLE 1

# Deterministic execution

Workflows control actions.

NOT prompts.

---

# PRINCIPLE 2

# Event-driven coordination

Everything becomes canonical events.

---

# PRINCIPLE 3

# State machine governance

All workflows have explicit states.

---

# PRINCIPLE 4

# AI is bounded

AI assists.

AI does not govern.

---

# PRINCIPLE 5

# Operational auditability

Everything replayable.

---

# PRINCIPLE 6

# Source-of-truth ownership

As required:

- Stripe → payments
- Recharge → subscriptions
- Shopify → orders

---

# 7. Data Ownership Model

| Domain | Source of Truth |
| --- | --- |
| Payment state | Stripe |
| Subscription state | Recharge |
| Order/customer state | Shopify |
| Workflow state | Jeeves |
| Escalation state | Jeeves |
| Policies | Jeeves |
| Timeline/audit | Jeeves |

---

# 8. Internal Architecture Style

# IMPORTANT

DO NOT build:

- distributed microservices;
- Kafka infra;
- event sourcing complexity.

---

# USE:

```
modular monolith
+
Postgres
+
Redis
+
background workers
```

---

# WHY

You need:

- speed;
- reliability;
- iteration;
- AI-codegen friendliness.

Not:

- infra complexity.

---

# 9. Suggested Module Structure

```
/core
    /events
    /workflows
    /policies
    /execution
    /commerce
    /escalations
    /timeline
    /ai
    /knowledge

/channels
    /widget
    /email

/integrations
    /stripe
    /recharge
    /shopify
    /tracking

/shared
    /db
    /redis
    /locks
    /idempotency
```

---

# 10. What Gets Deleted Architecturally

| Current Architecture | Fate |
| --- | --- |
| agent.run central orchestration | removed |
| generic tool loop | removed |
| conversational memory system | removed |
| generalized CRM abstraction | removed |
| AI-first orchestration | removed |
| generalized support positioning | removed |

---

# 11. What Becomes the New Product Core

# NEW PRODUCT CORE

```
Workflow Runtime
+
Policy Engine
+
Operational Execution
+
Commerce Domain Model
+
Audit Timeline
```

---

# 12. Biggest Strategic Insight

The target system is NOT:

```
customer support AI
```

It is:

```
operational coordination infrastructure
```

for subscription commerce.

That is the true architectural identity.