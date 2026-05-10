# Definition Doc

# 1. Market Fit

## 1.1 Pain Validation

### 1.1.1 Core problem

E-commerce brands operate customer workflows across fragmented systems: Shopify, Recharge, Stripe, Helpdesk, Email/WA,  Shipping/tracking systems. As a result, 

<aside>
<img src="https://www.notion.so/icons/report_yellow.svg" alt="https://www.notion.so/icons/report_yellow.svg" width="40px" />

high-frequency customer operations become: reactive, manual and inconsistent.

</aside>

### 1.1.2 Highest-pain  workflows

1. Revenue recovery: failed rebills; involuntary churn; cancellation requests.
2. Post-purchase support: WISMO (“Where is my order?”); shipping delays; shipment exceptions.
3. Customer operations overhead: repetitive support tickets; context switching; fragmented customer history.

### 1.1.3 Quantified market pain

Industry benchmarks consistently show:

- 20–40% of subscription churn is involuntary;
- failed payment recovery has direct measurable revenue impact;
- WISMO can account for 30–60% of ecommerce support volume;
- support operations scale linearly with order growth in most Shopify brands.

### 1.1.4 Current solution limitations

Existing tools solve isolated functions:

| Function | Existing Tools |
| --- | --- |
| Helpdesk | Gorgias / Zendesk |
| Subscriptions | Recharge |
| Payments | Stripe |
| Email/SMS | Klaviyo / Attentive |
| Tracking | ShipStation / tracking providers |

But workflows remain fragmented across systems.

Most current solutions:

- do not coordinate operational workflows end-to-end;
- do not maintain unified operational context;
- do not provide reliable workflow automation across customer operations.

## 1.2 Current Workflow

### Example: failed payment recovery

```
Failed rebill
→ support ticket created
→ agent checks Recharge
→ agent checks Stripe
→ customer contacted manually
→ retry scheduled manually
→ follow-up forgotten or delayed
```

### Example: WISMO handling

```
Customer asks “Where is my order?”
→ support agent opens tracking provider
→ checks shipment state
→ checks Shopify order
→ manually responds
→ handles escalation if delayed
```

## 1.3 Ideal Customer Profile

### 1.3.1 Initial ICP

Segment: 

> Shopify subscription ecommerce brands.
> 

Best-fit verticals: 

> Beauty; wellness; supplements; consumables.
> 

### 1.3.2 Business profile:

| Parameter | Target |
| --- | --- |
| GMV | $1M–15M |
| Team size | 10–50 |
| Support team | 2–10 |
| Geography | US / EU |
| Stack | Shopify + Recharge + Stripe |
| Business model | recurring purchase / subscription |
| Growth stage | scaling |

### 1.3.3 Buyer

Founder; CX manager; operations lead.

### 1.3.4 Primary users

Support team; CX manager; operations team.

## 1.4 Product Market Fit

### 1.4.1 Initial PMF wedge

<aside>
<img src="https://www.notion.so/icons/barcode_yellow.svg" alt="https://www.notion.so/icons/barcode_yellow.svg" width="40px" />

AI-powered revenue recovery and customer operations workflows

</aside>

for:

<aside>
<img src="https://www.notion.so/icons/user_yellow.svg" alt="https://www.notion.so/icons/user_yellow.svg" width="40px" />

Shopify subscription brands.

</aside>

### 1.4.2 Initial workflow focus

1. Failed payment recovery;
2. Cancellation save flows.
3. WISMO / order status handling.

# 2. Product Definition

## 2.1 Core Job To Be Done

<aside>
<img src="https://www.notion.so/icons/checkmark_yellow.svg" alt="https://www.notion.so/icons/checkmark_yellow.svg" width="40px" />

Help Shopify subscription brands recover revenue and automate repetitive customer operations without scaling support headcount.

</aside>

## 2.2 MVP Scope

#### 2.2.1 Failed payment recovery

Detect failed rebills → Customer outreach → payment method update flows → retry orchestration → recovery tracking escalation handling.

### 2.2.2 Cancellation save

Detect cancellation intent → offer pause/skip options → bounded save flows→ escalation when needed.

### 2.2.3 WISMO / order status

Order status retrieval → shipment visibility → automated customer responses → escalation for shipping exceptions.

## 2.3 Explicit MVP Non-Goals

<aside>
<img src="https://www.notion.so/icons/cut_yellow.svg" alt="https://www.notion.so/icons/cut_yellow.svg" width="40px" />

The MVP is NOT:

</aside>

- a generalized AI support agent;
- a helpdesk replacement;
- a CRM;
- a full omnichannel automation platform;
- a proactive lifecycle intelligence platform.

<aside>
<img src="https://www.notion.so/icons/target_yellow.svg" alt="https://www.notion.so/icons/target_yellow.svg" width="40px" />

The MVP focuses on:

</aside>

- high-frequency;
- operationally repetitive;
- measurable customer workflows.

## 2.4 MVP Experience

### 2.4.1 Onboarding

```
Connect Shopify
→ connect Recharge
→ connect Stripe
→ configure workflow policies
→ enable guided automation
```

### 2.4.2 Deployment model

Initial rollout includes:

- approval-first mode;
- workflow testing;
- constrained automation boundaries;
- gradual autonomy rollout.

### 2.4.3 Time-to-value targets

| Metric | Target |
| --- | --- |
| First workflow active | < 30 min |
| First recovery action | same day |
| First recovered revenue | < 3 days |
| Operational value visibility | same day |

## 2.5 Autonomy Model

### 2.5.1 Bounded autonomy

AI operates only inside:

- predefined workflows;
- merchant-defined policies;
- approved action boundaries.

### 2.5.2 Full-auto zone

- outreach;
- reminders;
- retry scheduling;
- order status handling;
- context retrieval;
- workflow coordination.

### 2.5.3 Approval-required zone

- discounts;
- incentives;
- credits;
- refunds;
- retention offers.

### 2.5.3. Human-only zone

- fraud;
- legal disputes;
- policy overrides;
- high-value compensation;
- exceptional operational cases.

## 2.6 Operational Reliability Layer

### 2.6.1 Core system primitives

The platform requires deterministic operational coordination.

Core primitives:

- workflow state machine;
- idempotent actions;
- retry coordination;
- execution guards;
- escalation states;
- event synchronization;
- operational replay;
- audit timeline.

### 2.6.2 Source-of-truth model

Operational consistency must be maintained across:

- Shopify;
- Recharge;
- Stripe;
- communication systems;
- shipping/tracking systems.

## 2.7 Trust Architecture

### Goal

<aside>
<img src="https://www.notion.so/icons/bullseye_yellow.svg" alt="https://www.notion.so/icons/bullseye_yellow.svg" width="40px" />

AI-assisted automation without black-box operational behavior.

</aside>

### 2.7.1 Core trust primitives

- audit logs;
- operational timeline;
- explainability;
- human escalation;
- workflow visibility;
- approval flows;
- policy boundaries.

### 2.7.2 Merchant policy controls

Configurable:

- allowed actions;
- retry limits;
- escalation thresholds;
- communication boundaries;
- approval requirements.

## 2.8 Channel Strategy

### P1 channels

| Channel | Role |
| --- | --- |
| Email | recovery + operational workflows |
| Onsite widget/chat | customer continuity |

### Later expansion

- SMS;
- WhatsApp;
- Instagram DM.

## 2.9 ROI Narrative

<aside>
<img src="https://www.notion.so/icons/gem_yellow.svg" alt="https://www.notion.so/icons/gem_yellow.svg" width="40px" />

Recovered subscription revenue.

</aside>

## Secondary ROI

- reduced involuntary churn;
- reduced support workload;
- faster customer operations;
- lower operational overhead;
- improved customer response time.

## 2.10 Integration Boundary

### 2.10.1 Mandatory

- [Shopify](https://www.shopify.com/?utm_source=chatgpt.com)
- [Recharge](https://rechargepayments.com/?utm_source=chatgpt.com)
- [Stripe](https://stripe.com/?utm_source=chatgpt.com)

### 2.10.2 Optional

- [Klaviyo](https://www.klaviyo.com/?utm_source=chatgpt.com)
- [Slack](https://slack.com/?utm_source=chatgpt.com)

### 2.10.3 Avoid early

- ERP systems;
- deep helpdesk sync;
- broad omnichannel integrations;
- generalized CRM complexity.

## 2.11 Expansion Logic

## Phase 1

Revenue recovery and customer operations:

- failed payments;
- cancellation save;
- WISMO.

## Phase 2

Operational support workflows:

- shipping exceptions;
- billing confusion resolution;
- ticket routing/triage.

## Phase 3

Broader customer operations:

- subscription modifications;
- omnichannel coordination;
- proactive support workflows.

### Phase 4

Retention intelligence layer:

- proactive churn prevention;
- lifecycle orchestration;
- retention optimization;
- operational intelligence.

## 2.12 Defensibility

### 2.12.1 Long-term moat

The moat compounds through:

- operational trust;
- workflow reliability;
- execution history;
- merchant policy graphs;
- recovery optimization data;
- workflow intelligence;
- customer operational memory.

## 2.12.2 Strategic advantage

Over time, the platform becomes:

- deeply embedded into operational workflows;
- difficult to replace without operational disruption;
- increasingly optimized through workflow-specific execution data.
