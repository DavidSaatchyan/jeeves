# Canonical Domain Model

Основа:

- Product Overview
- Definition Doc
- Workflow Requirements

---

# 1. Why Canonical Domain Model Matters

Сейчас в системе implicit model:

```
tenant
chat
tool
file
```

Это модель AI-support platform.

---

Но target MVP требует:

```
operational commerce workflow model
```

Без canonical domain model:

- workflows станут spaghetti;
- integrations будут inconsistent;
- state conflicts explode;
- AI coding станет хаотичным.

---

# 2. Domain Design Principles

---

# PRINCIPLE 1

# Canonical Internal State

Внутри Jeeves все должно иметь:

- единый формат;
- единый lifecycle;
- единые state semantics.

Даже если:

- Stripe;
- Recharge;
- Shopify;
- carriers

имеют разные модели.

---

# PRINCIPLE 2

# External Systems Are Sources-of-Truth

Как уже определено:

| Domain | Source of Truth |
| --- | --- |
| Payments | Stripe |
| Subscriptions | Recharge |
| Orders/customers | Shopify |

---

# PRINCIPLE 3

# Jeeves Owns Operational Coordination

Jeeves НЕ владеет:

- subscription truth;
- payment truth.

Jeeves владеет:

- workflows;
- retries;
- escalations;
- policies;
- orchestration.

---

# PRINCIPLE 4

# Explicit State Machines Everywhere

Каждая operational entity должна иметь:

- states;
- transitions;
- lifecycle.

---

# 3. Core Domain Map

# PRIMARY DOMAINS

```
Tenant
Customer
Subscription
Invoice
PaymentFailure
Order
Shipment
Workflow
Escalation
Policy
Communication
TimelineEvent
```

---

# 4. Tenant Domain

# ENTITY

## Tenant

Represents merchant/business.

---

## Core fields

```
tenant_id
name
plan
status
timezone
created_at
```

---

## Owns

- customers;
- workflows;
- policies;
- communications;
- escalations.

---

# 5. Customer Domain

# ENTITY

## Customer

Canonical cross-system customer identity.

---

# Purpose

Unifies:

- Shopify customer;
- Stripe customer;
- Recharge customer;
- communication identity.

---

# Core fields

```
customer_id
tenant_id

email
phone

shopify_customer_id
stripe_customer_id
recharge_customer_id

first_seen_at
last_seen_at

risk_level
sentiment_state
frustration_score
```

---

# Important

Customer becomes:

```
operational identity anchor
```

---

# Relationships

Customer owns:

- subscriptions;
- invoices;
- workflows;
- conversations;
- escalations.

---

# 6. Subscription Domain

# ENTITY

## Subscription

Canonical subscription state.

Source-of-truth:

```
Recharge
```

---

# Core fields

```
subscription_id
tenant_id
customer_id

external_subscription_id

status
plan_name
product_sku

renewal_date
started_at

subscription_age_days

pause_state
skip_state

mrr
currency
```

---

# Canonical states

```
active
paused
cancel_pending
cancelled
expired
payment_failed
```

---

# Important

Jeeves stores:

```
operational projection
```

NOT authoritative truth.

---

# 7. Invoice Domain

# ENTITY

## Invoice

Canonical billing/payment entity.

Source-of-truth:

```
Stripe
```

---

# Core fields

```
invoice_id
tenant_id
customer_id
subscription_id

external_invoice_id

status
amount_due
currency

payment_attempt_count
last_failure_reason

due_date
paid_at
```

---

# Canonical states

```
draft
open
paid
failed
void
uncollectible
```

---

# Important

Invoice drives:

- payment recovery workflows;
- retry eligibility;
- escalation.

---

# 8. PaymentFailure Domain

# ENTITY

## PaymentFailure

Operational failure object.

---

# WHY separate entity?

Because:

- workflows;
- retries;
- escalation;
- classification

need stable operational object.

---

# Core fields

```
payment_failure_id

invoice_id
subscription_id
customer_id

failure_type
failure_category

recoverability

attempt_number

detected_at
last_retry_at

workflow_id
```

---

# Recoverability states

```
recoverable
semi_recoverable
blocked
```

Defined directly in Requirements.

---

# 9. Order Domain

# ENTITY

## Order

Canonical commerce order.

Source-of-truth:

```
Shopify
```

---

# Core fields

```
order_id
customer_id
tenant_id

external_order_id

order_status
fulfillment_status

total_amount
currency

created_at
fulfilled_at
```

---

# 10. Shipment Domain

# ENTITY

## Shipment

Canonical shipment object.

---

# WHY separate from Order?

Because:

- split shipments;
- carrier lifecycle;
- delays;
- exceptions

need independent lifecycle.

---

# Core fields

```
shipment_id
order_id
customer_id

carrier
tracking_number

shipment_state
shipment_confidence

last_tracking_update

estimated_delivery
actual_delivery
```

---

# Canonical shipment states

Defined from Requirements normalization layer:

```
processing
fulfilled
in_transit
delayed
exception
delivered
unknown
```

---

# 11. Workflow Domain

# THE MOST IMPORTANT DOMAIN

---

# ENTITY

## Workflow

Canonical operational workflow instance.

---

# Workflow types

```
payment_recovery
cancellation_save
wismo
```

---

# Core fields

```
workflow_id
tenant_id
customer_id

workflow_type
workflow_state

status

started_at
updated_at
completed_at

priority
expiration_at

locked_until

escalation_state
```

---

# Important principle

Workflow owns:

```
operational coordination
```

---

# Workflow statuses

```
active
paused
completed
failed
expired
escalated
```

---

# 12. Workflow State Domain

# ENTITY

## WorkflowStateTransition

Explicit transition history.

---

# Core fields

```
transition_id
workflow_id

from_state
to_state

trigger_event

decision_reason

performed_by

timestamp
```

---

# Important

This becomes:

```
core replay/debug primitive
```

---

# 13. Escalation Domain

# ENTITY

## Escalation

Human intervention object.

---

# Core fields

```
escalation_id
workflow_id
customer_id

escalation_reason
severity

owner_id

status

created_at
resolved_at
```

---

# Canonical escalation states

```
open
assigned
in_progress
resolved
closed
```

---

# Escalation triggers

Defined in Requirements:

- frustration;
- ambiguity;
- conflicts;
- policy boundaries.

---

# 14. Policy Domain

# ENTITY

## PolicySet

Merchant operational governance.

---

# Core fields

```
policy_set_id
tenant_id

retry_policy
communication_policy
escalation_policy
approval_policy

enabled_workflows
```

---

# Important

Policies are:

```
deterministic governance layer
```

NOT prompts.

---

# 15. Communication Domain

# ENTITY

## Communication

Canonical customer communication object.

---

# Core fields

```
communication_id
workflow_id
customer_id

channel
direction

message_type

delivery_status

deduplication_key

sent_at
delivered_at
```

---

# Communication channels

```
email
widget
sms_future
whatsapp_future
```

---

# Important

Communications become:

```
workflow artifacts
```

NOT standalone chats.

---

# 16. Timeline Domain

# ENTITY

## TimelineEvent

Unified operational audit event.

---

# Core fields

```
event_id
tenant_id

entity_type
entity_id

event_type
event_source

payload

created_at
```

---

# Examples

```
payment_failed_detected
retry_scheduled
customer_contacted
shipment_delayed
workflow_escalated
policy_blocked_action
```

---

# Important

Timeline becomes:

```
system-wide observability backbone
```

---

# 17. AI Domain

# ENTITY

## AIInteraction

Bounded AI reasoning artifact.

---

# Purpose

Track:

- classifications;
- summaries;
- generated communication.

---

# Core fields

```
ai_interaction_id

workflow_id

interaction_type

input_context
output

confidence

created_at
```

---

# Important

AI interactions are:

```
advisory artifacts
```

NOT operational authority.

---

# 18. Domain Relationships

# HIGH-LEVEL GRAPH

```
Tenant
 ├── Customers
 │     ├── Subscriptions
 │     ├── Orders
 │     │     └── Shipments
 │     ├── Invoices
 │     │     └── PaymentFailures
 │     ├── Workflows
 │     │     ├── StateTransitions
 │     │     ├── Communications
 │     │     ├── Escalations
 │     │     └── AIInteractions
 │     └── TimelineEvents
 │
 └── PolicySets
```

---

# 19. Aggregate Boundaries

# IMPORTANT FOR IMPLEMENTATION

---

# Aggregate: Workflow

Owns:

- transitions;
- communications;
- escalations;
- retry state.

---

# Aggregate: Customer

Owns:

- subscriptions;
- invoices;
- orders.

---

# Aggregate: Shipment

Owns:

- tracking lifecycle;
- carrier normalization state.

---

# 20. Critical Modeling Insight

The BIGGEST architecture change:

---

# CURRENT MODEL

```
conversation-centric
```

---

# TARGET MODEL

```
workflow-centric
```

---

# THIS changes EVERYTHING

Because now:

- communication becomes workflow artifact;
- AI becomes workflow assistant;
- support becomes operational continuity;
- retries become state transitions;
- escalations become first-class entities.

---

# 21. What This Enables

Now you can build:

- deterministic workflows;
- replayable execution;
- proper locking;
- idempotency;
- audit timelines;
- escalation flows;
- operational reliability.

Without domain chaos.

---

# 22. Most Important Strategic Insight

You are NOT building:

```
AI customer support
```

You ARE building:

```
Operational coordination system for subscription commerce
```

with:

```
AI-assisted communication
```

That distinction is now reflected directly in the domain model.