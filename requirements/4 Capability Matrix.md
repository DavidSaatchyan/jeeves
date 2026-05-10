# Capability Matrix

(Current Platform → Target Operational Workflow MVP)

Основа:

- текущая система → Product Overview
- target MVP → Definition Doc
- workflow requirements → Scenarios

---

# 1. Matrix Legend

| Status | Meaning |
| --- | --- |
| ✅ Reuse | Mostly reusable |
| ⚠️ Refactor | Partial reuse, major redesign |
| ❌ Replace | Existing implementation not suitable |
| 🆕 New | Missing capability |

---

# 2. Platform & Infrastructure Layer

| Capability | Current State | Target Role | Decision | Reuse |
| --- | --- | --- | --- | --- |
| Multi-tenancy | Stable | Core foundation | ✅ Keep | 95% |
| Auth/JWT/API keys | Stable | Core foundation | ✅ Keep | 95% |
| Session/Auth middleware | Stable | Core foundation | ✅ Keep | 90% |
| PostgreSQL infra | Stable | Core persistence | ✅ Keep | 95% |
| Alembic migrations | Stable | Schema evolution | ✅ Keep | 95% |
| Deployment pipeline | Stable | Infra foundation | ✅ Keep | 90% |
| Docker/Railway infra | Stable | Infra foundation | ✅ Keep | 90% |
| Encryption/Fernet | Stable | Credential protection | ✅ Keep | 90% |
| SSRF protection | Stable | External execution safety | ✅ Keep | 85% |
| Rate limiting | Stable | Platform safety | ✅ Keep | 80% |
| Redis infra | Partial | Locks/cache/idempotency | ⚠️ Expand | 60% |
| Logging infra | Partial | Operational audit | ⚠️ Expand | 70% |

---

# 3. Channel Layer

| Capability | Current State | Target Role | Decision | Reuse |
| --- | --- | --- | --- | --- |
| Widget infrastructure | Mature | Primary support surface | ✅ Keep | 80% |
| Widget UI | Generic AI chat | Workflow-aware support UI | ⚠️ Refactor | 50% |
| REST API | Stable | Event/API ingress | ✅ Keep | 80% |
| Telegram channel | Working | Non-MVP | ❌ Deprioritize | 10% |
| WhatsApp channel | Working | Non-MVP | ❌ Deprioritize | 10% |
| Email workflows | Missing | Critical MVP channel | 🆕 Build | 0% |
| Notification engine | Primitive | Workflow comms | ⚠️ Rebuild | 20% |
| Conversation continuity | Partial | Human escalation continuity | ⚠️ Refactor | 50% |

---

# 4. AI & Knowledge Layer

| Capability | Current State | Target Role | Decision | Reuse |
| --- | --- | --- | --- | --- |
| OpenAI integration | Stable | Communication generation | ✅ Keep | 85% |
| Prompt assembly | Generic | Workflow-aware prompting | ⚠️ Refactor | 50% |
| Tool-calling loop | LLM-centric | Deterministic execution | ❌ Replace | 10% |
| Generalized RAG | Heavy/general | Lightweight FAQ continuity | ⚠️ Reduce scope | 40% |
| ChromaDB usage | Central | Secondary support layer | ⚠️ Reduce role | 40% |
| Embedding pipeline | Mature | Lightweight KB | ⚠️ Simplify | 50% |
| Knowledge ingestion | Complex | Minimal merchant KB | ⚠️ Simplify | 50% |
| Prompt injection defense | Good | Still needed | ✅ Keep | 80% |
| Moderation layer | Good | Still needed | ✅ Keep | 80% |
| AI response generation | Generic support | Operational communication | ⚠️ Refactor | 60% |
| AI classification | Primitive | Intent/failure classification | ⚠️ Expand | 50% |
| Sentiment/frustration detection | Missing | Escalation input | 🆕 Build | 0% |

---

# 5. Workflow & Execution Layer (TRUE CORE)

| Capability | Current State | Target Role | Decision | Reuse |
| --- | --- | --- | --- | --- |
| Workflow engine | Missing | Core orchestration | 🆕 Build | 0% |
| State machine engine | Missing | Deterministic transitions | 🆕 Build | 0% |
| Event ingestion system | Primitive | Operational backbone | 🆕 Build | 10% |
| Event bus | Missing | Workflow coordination | 🆕 Build | 0% |
| Policy engine | Missing | Merchant governance | 🆕 Build | 0% |
| Execution engine | Primitive tools | Deterministic actions | ⚠️ Rebuild | 30% |
| Idempotency system | Missing | Retry safety | 🆕 Build | 0% |
| Distributed locks | Missing | Concurrency safety | 🆕 Build | 0% |
| Retry orchestration | Missing | Payment recovery core | 🆕 Build | 0% |
| Workflow scheduler | Missing | Timed execution | 🆕 Build | 0% |
| Escalation engine | Primitive | Operational escalation | 🆕 Build | 5% |
| Approval engine | Missing | Human approval flows | 🆕 Build | 0% |
| Replay engine | Missing | Recovery/debugging | 🆕 Build | 0% |
| Conflict reconciliation | Missing | State consistency | 🆕 Build | 0% |
| Workflow expiration handling | Missing | Operational cleanup | 🆕 Build | 0% |
| Communication cadence engine | Missing | Retry/outreach pacing | 🆕 Build | 0% |

---

# 6. Commerce Domain Layer

| Capability | Current State | Target Role | Decision | Reuse |
| --- | --- | --- | --- | --- |
| Shopify integration | Partial | Core commerce source | ⚠️ Refactor | 50% |
| Stripe integration | Partial | Payment source-of-truth | ⚠️ Refactor | 50% |
| Recharge integration | Missing | Subscription source-of-truth | 🆕 Build | 0% |
| Shipment/tracking integrations | Missing | WISMO workflows | 🆕 Build | 0% |
| Generic CRM abstraction | Generic REST | Not core architecture | ❌ Replace | 20% |
| Customer profile model | Weak | Canonical customer state | ⚠️ Rebuild | 30% |
| Subscription model | Missing | Core operational entity | 🆕 Build | 0% |
| Invoice/payment model | Missing | Recovery workflows | 🆕 Build | 0% |
| Shipment model | Missing | WISMO workflows | 🆕 Build | 0% |
| Tracking normalization | Missing | Carrier abstraction | 🆕 Build | 0% |
| Operational context retrieval | Primitive | Workflow context engine | ⚠️ Rebuild | 30% |

---

# 7. Support & Communication Layer

| Capability | Current State | Target Role | Decision | Reuse |
| --- | --- | --- | --- | --- |
| Chat continuity | Basic | Unified customer experience | ⚠️ Refactor | 60% |
| FAQ answering | Good | Secondary support layer | ✅ Keep | 70% |
| Human escalation handoff | Primitive | Operational escalation | ⚠️ Rebuild | 30% |
| Support timeline | Weak | Full operational timeline | ❌ Replace | 20% |
| Communication templates | Missing | Workflow messaging | 🆕 Build | 0% |
| Delivery tracking | Missing | Reliable outreach | 🆕 Build | 0% |
| Message deduplication | Missing | Idempotent comms | 🆕 Build | 0% |
| Email delivery integration | Missing | Core outreach | 🆕 Build | 0% |
| Customer frustration handling | Missing | Escalation logic | 🆕 Build | 0% |

---

# 8. Operational Reliability Layer

| Capability | Current State | Target Role | Decision | Reuse |
| --- | --- | --- | --- | --- |
| Audit logging | Partial | Compliance/replay | ⚠️ Expand | 60% |
| Operational timeline | Missing | Core trust primitive | 🆕 Build | 0% |
| State transition logs | Missing | Deterministic traceability | 🆕 Build | 0% |
| Action traceability | Weak | Operational trust | ⚠️ Expand | 40% |
| Source-of-truth reconciliation | Missing | Multi-system consistency | 🆕 Build | 0% |
| Workflow observability | Missing | Operations monitoring | 🆕 Build | 0% |
| Failure recovery | Weak | Operational resilience | 🆕 Build | 10% |
| Dead-letter handling | Missing | Reliable execution | 🆕 Build | 0% |
| Timeout handling | Weak | Workflow lifecycle | ⚠️ Expand | 20% |
| SLA monitoring | Missing | Escalation governance | 🆕 Build | 0% |

---

# 9. Admin & Merchant Control Layer

| Capability | Current State | Target Role | Decision | Reuse |
| --- | --- | --- | --- | --- |
| Admin dashboard shell | Good | Merchant operations UI | ✅ Keep | 75% |
| Workflow visibility | Missing | Core trust surface | 🆕 Build | 0% |
| Operational timeline UI | Missing | Merchant trust layer | 🆕 Build | 0% |
| Workflow replay UI | Missing | Debugging/support | 🆕 Build | 0% |
| Policy management UI | Missing | Merchant governance | 🆕 Build | 0% |
| Approval queue UI | Missing | Human-in-loop ops | 🆕 Build | 0% |
| Escalation queue UI | Missing | Human support ops | 🆕 Build | 0% |
| Retry policy configuration | Missing | Recovery governance | 🆕 Build | 0% |
| Communication policy config | Missing | Outreach governance | 🆕 Build | 0% |
| Workflow analytics | Missing | ROI visibility | 🆕 Build | 0% |

---

# 10. Billing & Commercial Layer

| Capability | Current State | Target Role | Decision | Reuse |
| --- | --- | --- | --- | --- |
| Billing scaffolding | Exists | SaaS monetization | ⚠️ Expand | 50% |
| Stripe billing integration | Missing | Subscription billing | 🆕 Build | 0% |
| Usage metering | Primitive | Workflow-based pricing | ⚠️ Rebuild | 30% |
| Trial handling | Primitive | GTM support | ⚠️ Refactor | 50% |
| ROI reporting | Missing | PMF visibility | 🆕 Build | 0% |

---

# 11. Biggest Strategic Insight

The matrix reveals:

---

# CURRENT SYSTEM SHAPE

```
AI support platform
```

Strong in:

- chat infra;
- integrations groundwork;
- generic tooling;
- support surfaces.

Weak in:

- deterministic operations;
- workflows;
- execution reliability.

---

# TARGET SYSTEM SHAPE

```
Operational workflow infrastructure
```

Core gaps:

- workflow engine;
- policy engine;
- state machines;
- event processing;
- reliability primitives.

---

# 12. Most Important Technical Conclusion

This is NOT:

```
feature expansion
```

This IS:

```
execution model replacement
```

---

# 13. Reuse Reality

## High reuse

```
Infrastructure
Channels
Security
Deployment
Tenant system
Basic UI shell
```

---

## Medium reuse

```
Integrations
Widget UX
Support continuity
AI communication
```

---

## Low reuse

```
Agent orchestration
Conversation memory
Generic tool loop
```

---

## Entirely missing

```
Workflow OS core
```