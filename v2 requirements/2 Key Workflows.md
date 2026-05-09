# Requirements

# 0. Cross-Workflow Operational Guarantees

## 0.1 Deterministic Execution Boundary

LLM NEVER directly executes operational actions.

LLM responsibilities:

- classification;
- summarization;
- communication generation;
- bounded decision assistance.

Deterministic systems handle:

- workflow state transitions;
- policy validation;
- execution authorization;
- retries;
- synchronization;
- idempotency enforcement.

## 0.2 Idempotency Guarantees

All operational actions must be:

- retry-safe;
- deduplicated;
- replay-safe.

Applies to:

- retries;
- messages;
- subscription mutations;
- escalation creation.

## 0.3 State Ownership Rules

Define source-of-truth priority:

- Stripe → payment state;
- Recharge → subscription state;
- Shopify → customer/order state.

Conflicting states must trigger:

- reconciliation;
- escalation;
- workflow pause.

## 0.4 Escalation Guarantees

Automation must stop when:

- confidence insufficient;
- policy conflict detected;
- customer frustration threshold exceeded;
- operational ambiguity unresolved.

## 0.5 Auditability Guarantees

All workflow operations must log:

- state transitions;
- messages;
- retries;
- escalations;
- approvals;
- policy decisions.

## 0.6 Merchant Policy Engine

Merchant-defined policies control:

- allowed workflow actions;
- retry limits;
- escalation thresholds;
- communication cadence;
- approval requirements;
- automation boundaries.

Policy engine overrides AI-generated suggestions.

## 0.7 MVP Simplification Rules

MVP intentionally avoids:

- adaptive AI optimization;
- dynamic negotiation;
- autonomous policy generation;
- predictive orchestration;
- generalized multi-workflow agents.

Priority is: deterministic operational reliability.

# 1. Workflow Scenarios

## 1.1 Failed Payment Recovery

### 1.1.1 Workflow Objective

Recover failed subscription revenue safely and automatically while preventing duplicate actions, invalid retries, and customer frustration.

### 1.1.2 Workflow Triggers

Workflow starts when:

- Recharge emits failed rebill event;
- Stripe invoice/payment failure detected;
- subscription renewal payment fails.

### 1.1.3 Required Preconditions

Workflow activates only if:

- subscription status = active;
- invoice status = unpaid/open;
- no successful payment already recorded;
- no active recovery workflow exists;
- customer not already escalated manually;
- retry eligibility valid;
- merchant policy allows automated recovery.

### 1.1.4 Required Context Retrieval

System retrieves:

#### Subscription context

- subscription status;
- next renewal date;
- product/SKU;
- subscription age;
- prior skips/pauses;
- subscription value.

#### Billing context

- invoice status;
- payment failure reason;
- retry history;
- payment method status;
- prior failed invoices.

#### Customer context

- prior recovery attempts;
- support history;
- sentiment/escalation history;
- cancellation history.

#### Policy context

- retry limits;
- allowed outreach cadence;
- communication restrictions;
- escalation thresholds.

### Identity Resolution Constraints

Workflow must validate:

- customer identity consistency;
- active subscription ownership;
- duplicate customer records;
- email/payment identity conflicts.

### 1.1.5 Failure Type Classification

System classifies payment failure before any action.

#### 1.1.5.1 Recoverable failures

Examples:

- expired card;
- insufficient funds;
- temporary bank decline;
- authentication required.

Allowed:

- retry orchestration;
- customer outreach.

#### 1.1.5.2 Semi-recoverable failures

Examples:

- recurring hard declines;
- repeated insufficient funds;
- payment authentication issues.

Allowed:

- limited retries;
- escalation-aware communication.

#### 1.1.5.3 Non-recoverable / blocked

Examples:

- fraud flags;
- blocked payment method;
- disputed customer state;
- subscription canceled during workflow.

Must escalate or terminate workflow.

### 1.1.6 Workflow States

#### 1.1.6.1 Failed Payment Detected

System:

- creates workflow instance;
- locks duplicate workflow creation;
- persists operational snapshot.

#### 1.1.6.2 Eligibility Validation

Validate:

- invoice still unpaid;
- subscription active;
- customer not manually handled;
- retry still valid.

If validation fails:

- terminate workflow safely.

#### 1.1.6.3 Recovery Strategy Selection

Deterministic engine selects:

- retry timing;
- outreach timing;
- allowed communication sequence;
- escalation thresholds.

LLM does NOT select retry policy.

#### 1.1.6.4 Customer Outreach

Possible actions:

- payment update request;
- retry reminder;
- authentication assistance.

Rules:

- no duplicate messages;
- cooldown windows enforced;
- communication channel validated.

Outbound communication must support:

- message idempotency keys;
- delivery tracking;
- duplicate-send prevention.

#### 1.1.6.5 Awaiting Customer Action

Possible customer outcomes:

- payment updated;
- customer responds;
- customer ignores;
- customer requests cancellation;
- customer frustrated/confused.

#### 1.1.6.6 Retry Execution

Retry only if:

- retry window valid;
- payment method valid;
- no conflicting payment success;
- retry limit not exceeded.

Retry execution must be:

- idempotent;
- observable;
- verifiable.

#### 1.1.6.7 Resolution

Successful recovery:

- invoice paid;
- workflow closed;
- metrics updated.

Unsuccessful recovery (Possible outcomes)

- subscription churned;
- escalated to human;
- workflow timeout;
- retry limit exceeded.

#### 1.1.6.8 Workflow Expiration

Workflow terminates if:

- recovery window exceeded;
- retry limit exceeded;
- workflow inactive beyond timeout threshold;
- payment resolved externally.

Expired workflows must:

- close safely;
- persist audit state;
- prevent reactivation conflicts.

### 1.1.7 Critical Edge Cases

#### 1.1.7.1 Duplicate recovery prevention

Prevent:

- parallel workflows;
- duplicate retries;
- duplicate outreach.

Critical for reliability.

#### 1.1.7.2 Payment succeeds externally

Customer may:

- update card externally;
- pay manually;
- retry succeeds outside workflow.

Workflow must continuously re-check payment state.

#### 1.1.7.3 Customer cancellation during recovery

If cancellation initiated:

- pause recovery flow;
- transition into cancellation workflow.

#### 1.1.7.4 Recharge/Stripe desync

Possible:

- invoice states conflict;
- subscription status stale.

Must trigger escalation or reconciliation state.

#### 1.1.7.5 Authentication-required payments (3DS/SCA)

System must:

- detect authentication requirement;
- send proper action request;
- avoid blind retries.

#### 1.1.7.6 High-frustration customers

Signals:

- angry language;
- repeated contact;
- escalation requests.

Must reduce automation aggressiveness.

#### 1.1.7.7 Concurrent State Mutation

Workflow must safely handle:

- manual support intervention;
- customer portal updates;
- external payment success;
- simultaneous webhook events.

State conflicts require:

- workflow pause;
- revalidation;
- reconciliation.

### 1.1.8 Explicit MVP Rules

MVP does NOT support:

- adaptive retry optimization;
- AI-generated incentives;
- dynamic negotiation;
- unsupported payment processors;
- multi-subscription dependency handling.

## 1.2 Cancellation Save

### 1.2.1 Workflow Objective

Reduce avoidable churn while preserving customer trust and regulatory-safe cancellation handling.

### 1.2.3 Workflow Triggers

Workflow starts when:

- customer explicitly requests cancellation;
- cancellation intent detected in message;
- cancellation flow initiated from portal/chat/email.

### 1.2.4 Required Preconditions

Workflow activates only if:

- subscription active;
- save flow enabled by merchant;
- customer eligible for retention options;
- no active refund dispute;
- no compliance restriction applies.

### 1.2.5 Required Context Retrieval

#### 1.2.5.1 Subscription context

- plan type;
- renewal timing;
- subscription age;
- prior skips/pauses;
- prepaid status.

#### 1.2.5.2 Customer context

- cancellation history;
- support history;
- sentiment state;
- prior retention attempts.

#### 1.2.5.3 Merchant policy context

- allowed save options;
- retention restrictions;
- escalation rules;
- compliance requirements.

### 1.2.6 Cancellation Intent Classification

System classifies:

#### 1.2.6.1 Soft cancellation intent

Examples:

- “too much product”
- “need a break”
- “delivery too frequent”

Eligible for save flows.

#### 1.2.6.2 Hard cancellation intent

Examples:

- angry cancellation;
- trust loss;
- legal/compliance request.

Automation minimized.

#### 1.2.6.3 Billing/problem-driven cancellation

Examples:

- failed shipment;
- wrong charge;
- damaged order.

May require workflow transfer instead of save attempt.

### 1.2.7 Workflow States

#### 1.2.7.1 Cancellation Intent Detected

System:

- creates workflow;
- freezes duplicate retention attempts;
- retrieves operational context.

#### 1.2.7.2 Eligibility Evaluation

Determine:

- allowed save actions;
- prohibited offers;
- escalation conditions.

#### 1.2.7.3 Save Flow Selection

Allowed MVP save actions:

- pause subscription;
- skip next shipment;
- delay renewal.

No open-ended offer generation.

#### 1.2.7.4 Save Offer Communication

AI:

- explains options;
- adapts framing to customer context;
- avoids aggressive retention language.

Rules:

- cancellation path must remain accessible;
- no manipulative UX patterns.

Customer must always be able to:

- complete cancellation immediately;
- bypass retention flows;
- request human escalation.

#### 1.2.7.5 Customer Decision Handling

Possible outcomes:

- accepts save;
- rejects save;
- requests escalation;
- confirms cancellation;
- expresses frustration/confusion.

Retention attempts must enforce:

- maximum retry count;
- cooldown windows;
- anti-loop protection.

#### 1.2.7.6 Subscription Action Execution

Execute:

- pause;
- skip;
- delay;
- cancellation.

Execution requires:

- policy validation;
- workflow verification;
- action confirmation.

#### 1.2.7.7 Resolution

Possible outcomes:

- subscription retained;
- temporarily paused;
- cancellation completed;
- escalated to human.

### 1.2.8 Critical Edge Cases

#### 1.2.8.1 Regulatory-safe cancellation

System must:

- allow straightforward cancellation;
- avoid dark-pattern retention;
- avoid repeated blocking prompts.

#### 1.2.8.2 Prepaid subscriptions

Pause/skip logic may be unsupported.

Requires fallback handling.

#### 1.2.8.3 Bundle subscriptions

Subscription mutation may affect:

- inventory;
- shipment grouping;
- bundle logic.

May require escalation.

#### 1.2.8.4 Angry customers

If strong frustration detected:

- minimize retention pressure;
- shorten flow;
- escalate faster.

#### 1.2.8.5 Refund-linked cancellations

If cancellation tied to:

- refunds;
- disputes;
- charge complaints;

transfer to billing/support workflow.

### 1.2.9 Cancellation Compliance Logging

System must log:

- cancellation request timestamp;
- save attempts;
- customer decisions;
- cancellation completion state.

Required for:

- auditability;
- dispute defense;
- regulatory compliance.

### 1.2.10 Explicit MVP Rules

MVP does NOT support:

- dynamic discounts;
- AI-generated incentives;
- churn prediction;
- open negotiation;
- multi-step retention experimentation.

## 1.3 WISMO

### 1.3.1 Workflow Objective

Resolve repetitive order-status requests automatically while escalating operational exceptions safely.

### 1.3.2 Workflow Triggers

Workflow starts when:

- customer requests order status;
- shipment inquiry detected;
- delivery concern identified.

### 1.3.3 Required Preconditions

Workflow activates only if:

- order exists;
- customer identity verified;
- shipment data available or retrievable;
- no active shipping escalation already exists.

### 1.3.4 Required Context Retrieval

#### 1.3.4.1 Order context

- order status;
- fulfillment status;
- shipment status;
- tracking number;
- delivery estimate.

#### 1.3.4.2 Shipment context

- carrier state;
- tracking events;
- exception events;
- shipment age.

### 1.3.4.3 Customer context

- prior WISMO contacts;
- escalation history;
- sentiment/frustration signals.

### 1.3.5 Intent Classification

System classifies:

#### 1.3.5.1 Simple WISMO

Examples:

- “where is my order?”
- “has it shipped?”

Can fully automate.

#### 1.3.5.2 Delay concern

Examples:

- “it’s late”
- “tracking not moving”

May require exception evaluation.

#### 1.3.5.3 Escalation-risk inquiry

Examples:

- “package lost”
- “I need refund”
- “this is unacceptable”

Requires escalation-aware handling.

### 1.3.6 Workflow States

#### 1.3.6.1 Inquiry Detected

System:

- creates workflow;
- retrieves shipment state;
- checks existing escalations.

#### 1.3.6.2 Shipment State Normalization

Normalize carrier states into:

- processing;
- fulfilled;
- in transit;
- delayed;
- exception;
- delivered;
- unknown.

Critical because carriers differ heavily.

System must validate:

- tracking data recency;
- carrier update freshness;
- stale-event thresholds.

Stale tracking data must:

- reduce automation confidence;
- avoid definitive delivery claims.

#### 1.3.6.3 Response Strategy Selection

Determine:

- automated response;
- reassurance flow;
- escalation need;
- human intervention requirement.

If shipment confidence insufficient:

- avoid definitive statements;
- use uncertainty-aware messaging;
- escalate when required.

#### 1.3.6.4 Customer Communication

Possible responses:

- tracking update;
- ETA clarification;
- delay explanation;
- shipment reassurance.

Rules:

- avoid hallucinated delivery promises;
- never invent shipment status.

#### 1.3.6.5 Exception Handling

Escalate if:

- shipment stalled;
- carrier exception;
- lost package signals;
- repeated failed delivery;
- conflicting tracking data.

#### 1.3.6.6 Resolution

Possible outcomes:

- inquiry resolved;
- escalation created;
- manual review required.

### 1.3.7 Critical Edge Cases

#### 1.3.7.1 Missing tracking data

Possible causes:

- carrier delay;
- fulfillment sync issue;
- partial shipment.

Requires fallback messaging.

#### 1.3.7.2 Stale tracking events

Tracking may stop updating temporarily.

System must avoid:

- false “lost package” conclusions.

#### 1.3.7.3 Split shipments

Different items may have:

- separate tracking;
- separate fulfillment timing.

#### 1.3.7.4 Delivered-but-customer-claims-missing

High-risk workflow.

Must escalate quickly.

#### 1.3.7.5 Emotional escalation

Customer frustration can escalate rapidly in delivery workflows.

System must:

- detect frustration;
- reduce automation rigidity;
- escalate appropriately.

### 1.3.8 Explicit MVP Rules

MVP does NOT support:

- carrier dispute resolution;
- refund automation;
- proactive shipment monitoring;
- advanced logistics orchestration;
- international customs workflows.
