# Jeeves — Implementation Architecture v2

# 1. Purpose

This document defines the actual implementation blueprint for the Jeeves MVP.

It translates:
- Target System Architecture v2;
- Canonical Domain Model;
- Workflow State Machine Specifications;

into:
- code modules;
- runtime boundaries;
- database schemas;
- queue/scheduler mechanics;
- Redis usage;
- transaction rules;
- execution guarantees.

---

# 2. Architecture Style

## Target Runtime

```text
Modular Monolith
+
Postgres
+
Redis
+
Background Workers
```

---

## Why

MVP priorities:
- deterministic execution;
- speed of iteration;
- operational simplicity;
- AI-assisted development friendliness;
- transactional consistency.

NOT priorities:
- microservices;
- distributed infra;
- Kafka complexity;
- event sourcing.

---

# 3. Runtime Topology

# Components

```text
┌─────────────────────┐
│ FastAPI App         │
│ - APIs              │
│ - Channels          │
│ - Webhooks          │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ Event Layer         │
│ - normalization     │
│ - deduplication     │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ Workflow Runtime    │
│ - state machines    │
│ - transitions       │
│ - orchestration     │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ Execution Layer     │
│ - retries           │
│ - actions           │
│ - comms             │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ Integrations        │
│ - Stripe            │
│ - Recharge          │
│ - Shopify           │
└─────────────────────┘
```

---

# 4. Module Structure

```text
/app
    /api
    /channels
    /integrations
    /workers

/core
    /events
    /workflows
    /policies
    /execution
    /commerce
    /communications
    /escalations
    /timeline
    /ai
    /knowledge

/shared
    /db
    /redis
    /locks
    /idempotency
    /queue
    /utils
```

---

# 5. Core Runtime Components

# 5.1 Event Layer

## Purpose

Convert external signals into canonical events.

---

## Responsibilities

- normalize webhook payloads;
- deduplicate events;
- validate signatures;
- persist canonical events;
- dispatch workflow triggers.

---

## Modules

```text
/core/events
    base.py
    dispatcher.py
    deduplicator.py
    schemas.py
```

---

## Integration adapters

```text
/integrations/stripe/events.py
/integrations/recharge/events.py
/integrations/shopify/events.py
```

---

## Canonical event schema

```python
class CanonicalEvent:
    event_id: str
    tenant_id: str

    event_type: str
    event_source: str

    entity_type: str
    entity_id: str

    occurred_at: datetime

    payload: dict
```

---

## Event processing contract

Every event must:
- validate signature;
- acquire dedup lock;
- persist event;
- dispatch asynchronously.

---

# 5.2 Workflow Runtime

# MOST IMPORTANT COMPONENT

---

## Purpose

Deterministic workflow orchestration.

---

## Responsibilities

- workflow creation;
- state transitions;
- transition validation;
- lock management;
- expiration;
- retries;
- replay.

---

## Modules

```text
/core/workflows
    runtime.py
    registry.py
    transitions.py
    guards.py
    scheduler.py
    locks.py
```

---

## Workflow base contract

```python
class Workflow:
    workflow_id: str
    workflow_type: str
    current_state: str

    async def handle_event(self, event):
        pass

    async def transition(self, to_state):
        pass

    async def validate_transition(self):
        pass
```

---

## Workflow registry

```python
WORKFLOW_REGISTRY = {
    "payment_recovery": PaymentRecoveryWorkflow,
    "cancellation_save": CancellationSaveWorkflow,
    "wismo": WismoWorkflow,
}
```

---

# 5.3 State Machine Engine

## Purpose

Explicit transition governance.

---

## Structure

```python
PAYMENT_RECOVERY_TRANSITIONS = {
    "DETECTED": ["VALIDATING", "ESCALATED"],
    "VALIDATING": ["CLASSIFYING_FAILURE", "FAILED"],
}
```

---

## Transition validation

Every transition validates:
- allowed state path;
- workflow lock;
- policy compliance;
- entity consistency;
- expiration;
- escalation status.

---

# 5.4 Policy Engine

## Purpose

Merchant governance.

---

## Responsibilities

- retry limits;
- communication cadence;
- escalation thresholds;
- approval requirements.

---

## Modules

```text
/core/policies
    engine.py
    retry_rules.py
    escalation_rules.py
    communication_rules.py
```

---

## Example policy schema

```python
class RetryPolicy:
    max_attempts: int
    retry_windows: list[int]
    cooldown_minutes: int
```

---

## Critical rule

Policies override AI.

---

# 5.5 Execution Engine

## Purpose

Execute deterministic operational actions.

---

## Responsibilities

- payment retries;
- subscription mutations;
- communication dispatch;
- escalation creation.

---

## Modules

```text
/core/execution
    dispatcher.py
    guards.py
    audit.py
    idempotency.py
```

---

## Execution contract

Every action requires:

```python
class ExecutionContext:
    workflow_id: str
    idempotency_key: str
    policy_snapshot: dict
```

---

## Action interface

```python
class Action:
    async def validate(self):
        pass

    async def execute(self):
        pass
```

---

# 5.6 Communication Engine

## Purpose

Workflow-driven communication.

---

## Responsibilities

- email generation;
- widget messaging;
- delivery tracking;
- deduplication.

---

## Modules

```text
/core/communications
    service.py
    templates.py
    delivery.py
    deduplication.py
```

---

## Critical rules

Before sending:
- validate cadence;
- validate deduplication;
- validate escalation state.

---

# 5.7 Escalation Engine

## Purpose

Human intervention management.

---

## Responsibilities

- escalation creation;
- workflow pause;
- ownership tracking;
- SLA timers.

---

## Modules

```text
/core/escalations
    manager.py
    sla.py
    assignment.py
```

---

## Critical rule

Escalation pauses automation.

---

# 5.8 Timeline Engine

## Purpose

Operational observability.

---

## Responsibilities

- state transition logs;
- event logs;
- action history;
- replay support.

---

## Modules

```text
/core/timeline
    recorder.py
    replay.py
    queries.py
```

---

## Timeline event schema

```python
class TimelineEvent:
    event_type: str
    entity_type: str
    entity_id: str

    payload: dict
    created_at: datetime
```

---

# 5.9 AI Assistance Layer

## Purpose

Bounded AI support.

---

## Allowed capabilities

- intent classification;
- failure classification;
- communication generation;
- summarization;
- sentiment detection.

---

## Forbidden capabilities

- state transitions;
- execution authorization;
- retry decisions;
- workflow mutation.

---

## Modules

```text
/core/ai
    classifier.py
    sentiment.py
    generator.py
```

---

# 6. Database Architecture

# IMPORTANT

Postgres is:
- source of workflow truth;
- operational timeline store;
- workflow persistence layer.

---

# 6.1 Core Tables

## workflows

```sql
id
workflow_type
workflow_state
status
customer_id
subscription_id
started_at
completed_at
expiration_at
locked_until
```

---

## workflow_transitions

```sql
id
workflow_id
from_state
to_state
trigger_event
decision_reason
created_at
```

---

## canonical_events

```sql
id
event_type
event_source
entity_type
entity_id
payload
occurred_at
```

---

## retry_attempts

```sql
id
workflow_id
attempt_number
status
scheduled_at
executed_at
idempotency_key
```

---

## communications

```sql
id
workflow_id
channel
message_type
delivery_status
deduplication_key
sent_at
```

---

## escalations

```sql
id
workflow_id
reason
severity
status
assigned_to
created_at
```

---

## timeline_events

```sql
id
entity_type
entity_id
event_type
payload
created_at
```

---

# 7. Redis Architecture

# Redis responsibilities ONLY

- locks;
- queues;
- short-lived cache;
- idempotency windows;
- schedulers.

NOT source-of-truth.

---

# 7.1 Redis Keys

## Workflow locks

```text
workflow_lock:{workflow_id}
```

---

## Idempotency keys

```text
idempotency:{key}
```

---

## Scheduled retries

```text
retry_schedule:{workflow_id}
```

---

## Event deduplication

```text
event_dedup:{event_id}
```

---

# 8. Queue & Worker Architecture

# IMPORTANT

DO NOT use:
- Celery complexity;
- Kafka;
- distributed orchestration.

---

## Recommended

```text
RQ / ARQ / Dramatiq
```

Simple Redis-backed workers.

---

# 8.1 Worker Types

## Event workers

Responsibilities:
- process canonical events;
- dispatch workflows.

---

## Workflow workers

Responsibilities:
- execute transitions;
- schedule retries;
- expiration handling.

---

## Communication workers

Responsibilities:
- send emails;
- send widget messages;
- update delivery state.

---

## Reconciliation workers

Responsibilities:
- reload source-of-truth;
- detect conflicts;
- pause workflows.

---

# 9. Locking Strategy

# CRITICAL

Prevents:
- duplicate retries;
- parallel workflows;
- race conditions.

---

# 9.1 Workflow Lock

Every active workflow acquires:

```text
workflow_lock:{workflow_id}
```

TTL refreshed continuously.

---

# 9.2 Entity Lock

Prevent concurrent mutations:

```text
subscription_lock:{subscription_id}
invoice_lock:{invoice_id}
```

---

# 9.3 Lock acquisition contract

```python
async with workflow_lock(workflow_id):
    execute_transition()
```

---

# 10. Idempotency Architecture

# CRITICAL MVP REQUIREMENT

Defined explicitly in Requirements.

---

# 10.1 Idempotent Actions

All actions require:

```python
idempotency_key
```

---

## Example format

```text
payment_retry:{invoice_id}:{attempt_number}
```

---

# 10.2 Deduplication flow

Before action:

```python
if idempotency_exists(key):
    return existing_result
```

---

# 11. Scheduling Architecture

# Purpose

Support:
- retry scheduling;
- workflow expiration;
- cadence delays;
- reconciliation checks.

---

# 11.1 Scheduler

Simple worker polling scheduled jobs.

---

## Job schema

```python
class ScheduledJob:
    job_type: str
    execute_at: datetime
    payload: dict
```

---

# 12. Integration Architecture

# IMPORTANT

Integrations become:

```text
strict domain adapters
```

NOT generic CRM connectors.

---

# 12.1 Stripe Adapter

Responsibilities:
- invoice retrieval;
- retry execution;
- payment state;
- payment failures.

---

# 12.2 Recharge Adapter

Responsibilities:
- subscription mutations;
- pause/skip/delay;
- subscription state.

---

# 12.3 Shopify Adapter

Responsibilities:
- customer retrieval;
- order retrieval;
- fulfillment state.

---

# 13. Transaction Boundaries

# IMPORTANT

Every transition executes inside:

```text
single DB transaction
```

---

## Transition transaction includes

- transition persistence;
- state update;
- timeline event;
- retry scheduling;
- audit record.

---

## NEVER include

External API calls inside DB transaction.

---

# Correct pattern

```text
1. persist transition intent
2. commit transaction
3. execute external action
4. persist result event
```

---

# 14. Error Handling Strategy

# 14.1 External API Failures

Never crash workflow runtime.

Instead:
- persist failure;
- retry safely;
- escalate if threshold exceeded.

---

# 14.2 Reconciliation Conflicts

Transition workflow to:

```text
PAUSED_RECONCILIATION
```

---

# 14.3 Worker Crashes

Safe because:
- workflow state persisted;
- idempotency enforced;
- transitions replayable.

---

# 15. API Architecture

# Public APIs

```text
/api/widget
/api/events
/api/webhooks
```

---

# Internal APIs

```text
/internal/workflows
/internal/escalations
/internal/timeline
```

---

# IMPORTANT

Internal APIs are:

```text
workflow-centric
```

NOT chat-centric.

---

# 16. UI Architecture

# Widget UI

Becomes:

```text
workflow continuity surface
```

NOT generic AI assistant.

---

# Merchant Dashboard

Core sections:

```text
Workflows
Escalations
Timeline
Policies
Retries
Analytics
```

---

# 17. MVP Build Order

# PHASE 1

Core runtime:

```text
Canonical events
Workflow runtime
State machine engine
Timeline
Redis locks
```

---

# PHASE 2

Payment recovery:

```text
Stripe adapter
Retry engine
Email delivery
Policy engine
```

---

# PHASE 3

Cancellation workflows:

```text
Recharge adapter
Save flows
Escalation engine
```

---

# PHASE 4

WISMO:

```text
Shipment normalization
Tracking adapters
Risk classification
```

---

# PHASE 5

Support continuity:

```text
Lightweight KB
FAQ support
Continuity chat
```

---

# 18. Biggest Engineering Insight

The core system is NOT:

```text
AI orchestration
```

The core system IS:

```text
deterministic workflow runtime
```

with:

```text
AI-assisted communication
```

---

# 19. Final Architecture Identity

Jeeves becomes:

```text
Operational Workflow Infrastructure
for Subscription Commerce
```

NOT:

```text
generic AI support chatbot
```

That distinction must remain visible in:
- code structure;
- runtime ownership;
- DB schemas;
- workflow engine;
- UI;
- product positioning.

