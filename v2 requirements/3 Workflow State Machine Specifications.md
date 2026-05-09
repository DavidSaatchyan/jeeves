# Workflow State Machine Specifications (MVP)

Основа:

- Definition Doc
- Workflow Requirements
- Canonical Domain Model (previous step)

---

# 1. Purpose

This document defines:

```
deterministic workflow execution contracts
```

for:

- state transitions;
- retries;
- escalation;
- expiration;
- workflow coordination.

---

# 2. Global Workflow Runtime Rules

# Applies to ALL workflows

---

# 2.1 Deterministic Execution Rule

LLM NEVER:

- changes workflow state;
- authorizes execution;
- schedules retries;
- performs actions.

LLM MAY:

- classify;
- summarize;
- generate communication.

Defined explicitly in Requirements.

---

# 2.2 Single Active Workflow Lock

Rule:

```
Only one active workflow of the same type
per customer/subscription/order context.
```

---

# Purpose

Prevents:

- duplicate retries;
- duplicate outreach;
- conflicting actions.

---

# 2.3 Idempotency Rule

ALL actions require:

```
idempotency_key
```

Applies to:

- retries;
- emails;
- subscription mutations;
- escalations.

---

# 2.4 State Transition Rule

All transitions require:

```
transition validation
```

Validation checks:

- current state;
- allowed transition;
- workflow lock;
- policy compliance;
- source-of-truth consistency.

---

# 2.5 Workflow Expiration Rule

Every workflow has:

```
expiration_at
```

Expired workflows:

- terminate safely;
- release locks;
- preserve audit history.

---

# 2.6 Escalation Override Rule

Escalation pauses automation immediately.

---

# Escalation causes

- ambiguity;
- policy conflict;
- customer frustration;
- reconciliation conflict;
- repeated failures.

Defined in Requirements.

---

# 2.7 Source-of-Truth Revalidation Rule

Before ANY action:

- reload canonical state from source system.

Example:

- Stripe before retry;
- Recharge before cancellation mutation.

---

# 3. Failed Payment Recovery Workflow

# WORKFLOW TYPE

```
payment_recovery
```

---

# 3.1 Workflow Objective

Recover failed subscription revenue safely and deterministically.

---

# 3.2 Trigger Events

```
payment_failed
invoice_payment_failed
rebill_failed
```

---

# 3.3 Preconditions

Workflow starts ONLY IF:

```
subscription.active == true
invoice.status in [open, unpaid]
no_existing_active_workflow == true
retry_eligible == true
not_manually_escalated == true
```

Defined in Requirements.

---

# 3.4 State Machine

# STATES

```
DETECTED
VALIDATING
CLASSIFYING_FAILURE
SELECTING_STRATEGY
OUTREACH_PENDING
OUTREACH_SENT
WAITING_CUSTOMER
RETRY_SCHEDULED
RETRY_PENDING
RETRYING
VERIFYING_RESULT
RECOVERED
FAILED
ESCALATED
EXPIRED
PAUSED_RECONCILIATION
```

---

# 3.5 State Definitions

---

# DETECTED

# Entry trigger

External event received.

---

# Actions

- create workflow;
- acquire workflow lock;
- persist operational snapshot;
- write timeline event.

---

# Allowed transitions

```
→ VALIDATING
→ ESCALATED
```

---

# VALIDATING

# Purpose

Validate workflow eligibility.

---

# Validation checks

```
invoice still unpaid
subscription still active
retry allowed
workflow not duplicated
customer not escalated
```

---

# Failure outcomes

```
validation_failed
→ FAILED
```

---

# Allowed transitions

```
→ CLASSIFYING_FAILURE
→ FAILED
→ ESCALATED
```

---

# CLASSIFYING_FAILURE

# Purpose

Classify payment failure recoverability.

---

# AI allowed

YES:

- classification assistance.

---

# AI forbidden

NO:

- retry decisions.

---

# Output categories

Defined in Requirements.

```
recoverable
semi_recoverable
blocked
```

---

# Allowed transitions

```
recoverable → SELECTING_STRATEGY
semi_recoverable → SELECTING_STRATEGY
blocked → ESCALATED
```

---

# SELECTING_STRATEGY

# Purpose

Deterministically select retry strategy.

---

# Inputs

- merchant policy;
- retry history;
- failure category;
- customer sentiment;
- subscription value.

---

# Outputs

```
retry_schedule
communication_plan
escalation_threshold
```

---

# Allowed transitions

```
→ OUTREACH_PENDING
→ RETRY_SCHEDULED
→ ESCALATED
```

---

# OUTREACH_PENDING

# Purpose

Prepare communication.

---

# Actions

- generate communication;
- validate cadence;
- validate deduplication.

---

# Allowed transitions

```
→ OUTREACH_SENT
→ ESCALATED
```

---

# OUTREACH_SENT

# Actions

- send email/widget message;
- persist delivery status;
- store idempotency key.

---

# Allowed transitions

```
→ WAITING_CUSTOMER
→ RETRY_SCHEDULED
```

---

# WAITING_CUSTOMER

# Possible events

```
payment_method_updated
customer_replied
customer_cancel_requested
customer_frustrated
timeout_elapsed
external_payment_success
```

---

# Allowed transitions

```
payment_method_updated → RETRY_PENDING
external_payment_success → RECOVERED
customer_cancel_requested → ESCALATED
customer_frustrated → ESCALATED
timeout_elapsed → RETRY_SCHEDULED
```

---

# RETRY_SCHEDULED

# Actions

- enqueue retry job;
- persist retry window;
- schedule execution.

---

# Allowed transitions

```
→ RETRY_PENDING
→ EXPIRED
```

---

# RETRY_PENDING

# Purpose

Waiting for retry execution time.

---

# Guards

Before retry:

- reload Stripe state;
- validate no external success;
- validate retry limit.

---

# Allowed transitions

```
→ RETRYING
→ RECOVERED
→ FAILED
→ ESCALATED
```

---

# RETRYING

# Actions

- execute retry;
- record execution;
- persist idempotency key.

---

# Allowed transitions

```
→ VERIFYING_RESULT
→ ESCALATED
```

---

# VERIFYING_RESULT

# Actions

Reload authoritative Stripe invoice state.

---

# Allowed transitions

```
payment_success → RECOVERED
payment_failed → WAITING_CUSTOMER
retry_limit_exceeded → FAILED
reconciliation_conflict → PAUSED_RECONCILIATION
```

---

# PAUSED_RECONCILIATION

# Purpose

Handle source-of-truth conflicts.

---

# Examples

- Stripe/ReCharge desync;
- external manual intervention;
- conflicting states.

---

# Allowed transitions

```
→ VALIDATING
→ ESCALATED
→ FAILED
```

---

# RECOVERED

# Terminal state

---

# Actions

- close workflow;
- release locks;
- update metrics;
- write timeline event.

---

# FAILED

# Terminal state

Reasons:

- retry limit exceeded;
- ineligible;
- timeout;
- unrecoverable failure.

---

# ESCALATED

# Terminal automation state

Human ownership begins.

---

# EXPIRED

# Terminal state

Workflow exceeded:

- retry window;
- inactivity threshold;
- expiration policy.

---

# 4. Cancellation Save Workflow

# WORKFLOW TYPE

```
cancellation_save
```

---

# STATES

```
INTENT_DETECTED
VALIDATING
CLASSIFYING_INTENT
SELECTING_SAVE_FLOW
SAVE_OFFER_PENDING
SAVE_OFFER_SENT
WAITING_CUSTOMER_DECISION
EXECUTING_ACTION
RETAINED
CANCELLED
ESCALATED
FAILED
EXPIRED
```

---

# 4.1 Important Constraints

Defined in Requirements:

- cancellation must remain accessible;
- no dark patterns;
- no infinite retention loops.

---

# 4.2 Intent Classification Outputs

```
soft_intent
hard_intent
billing_problem
```

Defined in Requirements.

---

# 4.3 Save Actions Allowed

MVP ONLY:

```
pause_subscription
skip_next_shipment
delay_renewal
```

Defined in Definition Doc.

---

# 4.4 Critical Transitions

```
hard_intent → ESCALATED
billing_problem → ESCALATED
save_accepted → EXECUTING_ACTION
save_rejected → CANCELLED
customer_frustrated → ESCALATED
```

---

# 4.5 EXECUTING_ACTION

# Guards

Before execution:

- reload Recharge state;
- validate policy;
- validate eligibility;
- validate subscription still active.

---

# Allowed outcomes

```
pause_success → RETAINED
skip_success → RETAINED
delay_success → RETAINED
execution_failure → ESCALATED
```

---

# 5. WISMO Workflow

# WORKFLOW TYPE

```
wismo
```

---

# STATES

```
INQUIRY_DETECTED
VALIDATING_IDENTITY
RETRIEVING_SHIPMENT
NORMALIZING_SHIPMENT_STATE
CLASSIFYING_RISK
RESPONSE_PENDING
RESPONSE_SENT
WAITING_CUSTOMER
ESCALATED
RESOLVED
FAILED
EXPIRED
```

---

# 5.1 Shipment Normalization Outputs

Defined in Requirements.

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

# 5.2 Risk Classification Outputs

```
simple_wismo
delay_concern
escalation_risk
```

---

# 5.3 Critical Escalation Conditions

```
shipment_stalled
carrier_exception
lost_package_signal
delivered_but_missing
high_customer_frustration
conflicting_tracking_data
```

Defined in Requirements.

---

# 5.4 RESPONSE_PENDING

# AI responsibilities

Allowed:

- generate reassurance;
- explain tracking state;
- summarize ETA.

Forbidden:

- invent shipment status;
- promise delivery dates.

---

# Allowed transitions

```
→ RESPONSE_SENT
→ ESCALATED
```

---

# 5.5 RESOLVED

# Terminal state

Conditions:

- customer reassured;
- shipment visibility sufficient;
- no escalation required.

---

# 6. Shared Escalation State Machine

# ENTITY

```
Escalation
```

---

# STATES

```
OPEN
ASSIGNED
IN_PROGRESS
WAITING_EXTERNAL
RESOLVED
CLOSED
```

---

# Important rule

Workflow automation pauses while escalation active.

---

# 7. Shared Communication State Machine

# ENTITY

```
Communication
```

---

# STATES

```
PENDING
GENERATED
QUEUED
SENT
DELIVERED
FAILED
DEDUPLICATED
```

---

# Critical rule

No duplicate outreach.

Must validate:

```
deduplication_key
```

before sending.

---

# 8. Shared Retry State Machine

# ENTITY

```
RetryAttempt
```

---

# STATES

```
SCHEDULED
PENDING
EXECUTING
SUCCEEDED
FAILED
BLOCKED
```

---

# 9. Shared Workflow Runtime Contracts

# 9.1 Every workflow must support

```
pause()
resume()
expire()
escalate()
replay()
revalidate()
```

---

# 9.2 Every transition must persist

```
from_state
to_state
trigger_event
decision_reason
policy_snapshot
timestamp
```

---

# 9.3 Every workflow must support

```
idempotent replay
```

---

# 10. Most Important Architecture Insight

This specification transforms the product from:

```
chatbot logic
```

into:

```
deterministic operational runtime
```

---

# 11. What This Enables

Now you can safely implement:

- workflow engine;
- retry scheduler;
- escalation system;
- execution guards;
- audit replay;
- policy enforcement;
- deterministic automation.

Without AI chaos.