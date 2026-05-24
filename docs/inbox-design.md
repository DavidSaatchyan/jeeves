# Inbox & Operations Center — Design Document

## 1. Analysis & Motivation

### 1.1 Current State

The existing codebase processes customer messages through a fully automated pipeline:

```
Widget Chat → Intent Classifier → Workflow Engine → AI Response → ChatLog
```

**Problems this creates:**

| Gap | Impact |
|-----|--------|
| No unified conversation view | Operator cannot see "who is talking right now" |
| No conversation lifecycle | ChatLog is a flat log table, not a conversation entity |
| No operator assignment | All conversations are unowned. No one is responsible. |
| No handoff trigger | When AI fails or escalation is needed, there is no mechanism to route to a human |
| Customer identity is fragmented | `ChatLog.user_id` (text field), `Customer` model, `workflow.customer_id` — all separate |
| No conversation status tracking | No `active`, `waiting`, `escalated`, `closed` status on conversations |
| Workflow timeline is separate from chat | `TimelineEvent` and `ChatLog` live in different tables with no unified view |

### 1.2 What Crisp Does Well (Reference)

Crisp's core inbox strengths:
- **Unified conversation list** — all channels in one sorted list with status, preview, assignee
- **Customer sidebar** — rich profile with attributes, history, active sessions
- **Human handoff** — seamless transfer from bot to agent with full context
- **Typing preview** — agent sees what customer is typing before they send

**Where Crisp falls short (Jeeves opportunity):**
- Conversations are "chat threads" only — no connection to operational workflows
- No workflow state visible in the inbox
- Agent cannot see "this customer's order is delayed" without leaving the inbox
- No proactive action UI — agent can't trigger a refund or update from the inbox

### 1.3 Design Goals

1. **Operator sees everything in one place** — conversations, workflow state, customer info
2. **Conversation lifecycle** — every customer interaction has a status, assignee, and history
3. **Human handoff is a first-class concept** — AI runs until it can't, then seamlessly transfers
4. **Customer profile is enriched** — orders, subscriptions, past conversations, risk score
5. **Workflow state is visible from the inbox** — agent sees "order #1234: delayed, escalated"

---

## 2. Data Model

### 2.1 New Models

```python
class ConversationState(str, enum.Enum):
    ACTIVE = "active"           # AI is handling, no human needed yet
    WAITING = "waiting"         # Waiting for customer response
    HANDOFF_REQUESTED = "handoff_requested"  # AI requested human intervention
    ASSIGNED = "assigned"       # Human operator is handling
    CLOSED = "closed"           # Resolved, archived


class Conversation(Base):
    """A customer conversation — the core inbox entity.

    Replaces the flat ChatLog->session_id approach with a first-class
    conversation lifecycle. One Conversation has many Messages.
    """
    __tablename__ = "conversations"

    id: UUID = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: UUID = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)

    # Identity
    customer_id: UUID | None = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True, index=True)
    user_id: str = Column(Text, nullable=False, index=True)  # canonical external ID (email, shopify_customer_id)
    user_display_name: str | None = Column(Text, nullable=True)
    channel: str = Column(String(32), nullable=False, default="web_widget")  # web_widget, email, whatsapp, telegram

    # Status & assignment
    status: ConversationState = Column(String(32), nullable=False, default=ConversationState.ACTIVE, index=True)
    assigned_to: str | None = Column(Text, nullable=True)  # operator email (same as tenant email in MVP)
    assigned_at: DateTime | None = Column(DateTime, nullable=True)

    # Routing
    workflow_id: UUID | None = Column(UUID(as_uuid=True), ForeignKey("workflows.id"), nullable=True)
    workflow_type: str | None = Column(String(64), nullable=True)
    escalation_id: UUID | None = Column(UUID(as_uuid=True), ForeignKey("escalations.id"), nullable=True)

    # Timestamps
    started_at: DateTime = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_message_at: DateTime = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    closed_at: DateTime | None = Column(DateTime, nullable=True)
    created_at: DateTime = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: DateTime = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Preview
    last_message_preview: str | None = Column(Text, nullable=True)
    message_count: int = Column(Integer, default=0, nullable=False)
    unread_count: int = Column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("ix_conversations_tenant_status", "tenant_id", "status"),
        Index("ix_conversations_tenant_user", "tenant_id", "user_id"),
    )


class MessageDirection(str, enum.Enum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"
    NOTE = "note"  # internal operator note


class Message(Base):
    """A single message in a conversation.

    Replaces the dual-purpose ChatLog (which stored both query and response
    in the same row) with a proper message-per-row model.
    """
    __tablename__ = "messages"

    id: UUID = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: UUID = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    conversation_id: UUID = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False, index=True)

    direction: MessageDirection = Column(String(16), nullable=False)
    content: str = Column(Text, nullable=False)
    content_type: str = Column(String(32), default="text")  # text, image, action, system_event

    # Sender metadata
    sender_type: str = Column(String(16), nullable=False, default="customer")  # customer, ai, operator, system
    operator_id: str | None = Column(Text, nullable=True)  # if sent by an operator

    # Workflow context
    workflow_id: UUID | None = Column(UUID(as_uuid=True), ForeignKey("workflows.id"), nullable=True)
    workflow_state: str | None = Column(String(64), nullable=True)

    # AI metadata
    sources: dict | None = Column(JSONB, nullable=True)  # RAG retrieval traces
    confidence: float | None = Column(Float, nullable=True)

    # Delivery
    delivered: bool = Column(Boolean, default=False)
    read_at: DateTime | None = Column(DateTime, nullable=True)

    created_at: DateTime = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )


class OperatorNote(Base):
    """Internal operator notes attached to conversations."""
    __tablename__ = "operator_notes"

    id: UUID = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id: UUID = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    conversation_id: UUID = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False, index=True)
    content: str = Column(Text, nullable=False)
    operator_id: str = Column(Text, nullable=False)
    created_at: DateTime = Column(DateTime, default=datetime.utcnow, nullable=False)
```

### 2.2 Migrating from ChatLog

The `ChatLog` table stays for backward compatibility during migration. The widget and chat
routes will write to **both** `Message` + `Conversation` (new) and `ChatLog` (old) during a
transition period. Once the new inbox is stable, `ChatLog` writes can be removed.

**Migration strategy:**

```
Phase 1 (Write-path change):
POST /widget/chat → write to Message + Conversation  (dual-write to ChatLog)
POST /chat        → write to Message + Conversation  (dual-write to ChatLog)

Phase 2 (Read-path change):
GET /widget/inbox → read from Message instead of ChatLog

Phase 3 (Cleanup):
Remove ChatLog writes. Drop ChatLog table.
```

### 2.3 Customer Model Enrichment

The existing `Customer` model needs enrichment for the inbox profile:

```python
# Enrich the existing Customer model:
class Customer(Base):
    # ... existing columns ...

    # New columns for inbox profile
    display_name: str | None = Column(Text, nullable=True)
    avatar_url: str | None = Column(Text, nullable=True)
    timezone: str | None = Column(String(64), nullable=True)
    locale: str | None = Column(String(16), nullable=True)
    tags: list = Column(JSONB, nullable=True, default=list)

    # Activity
    total_conversations: int = Column(Integer, default=0)
    total_workflows: int = Column(Integer, default=0)
    last_seen_at: DateTime | None = Column(DateTime, nullable=True)
    last_message_at: DateTime | None = Column(DateTime, nullable=True)

    # Aggregated risk
    risk_level: str | None = Column(String(16), nullable=True)  # low, medium, high
    frustration_score: float | None = Column(Float, nullable=True)
    sentiment_trend: str | None = Column(String(16), nullable=True)  # improving, worsening, stable
```

---

## 3. API Design

### 3.1 Inbox API (new endpoints)

```
GET    /admin/api/inbox/conversations          — List conversations with filters
GET    /admin/api/inbox/conversations/{id}     — Get conversation detail
GET    /admin/api/inbox/conversations/{id}/messages  — Get messages (paginated)
POST   /admin/api/inbox/conversations/{id}/assign    — Assign to operator
POST   /admin/api/inbox/conversations/{id}/close     — Close conversation
POST   /admin/api/inbox/conversations/{id}/notes     — Add operator note
GET    /admin/api/inbox/conversations/{id}/notes     — Get operator notes
POST   /admin/api/inbox/messages/send           — Send message as operator
POST   /admin/api/inbox/conversations/{id}/takeover  — Take over from AI
```

#### GET /admin/api/inbox/conversations

```
Query params:
  status      — active, waiting, handoff_requested, assigned, closed (default: all)
  channel     — web_widget, email, whatsapp (optional)
  assignee    — operator email, "unassigned", "me" (optional)
  q           — full-text search across messages and customer info
  sort        — last_message_at (default), created_at
  order       — desc (default), asc
  limit       — default 50, max 200
  offset      — default 0

Response:
{
  "conversations": [
    {
      "id": "uuid",
      "customer": {
        "id": "uuid",
        "display_name": "Alice Johnson",
        "email": "alice@example.com",
        "avatar_url": null
      },
      "channel": "web_widget",
      "status": "active",
      "assigned_to": null,
      "workflow": {
        "id": "uuid",
        "type": "wismo",
        "state": "CLASSIFYING_RISK",
        "status": "active"
      },
      "last_message_preview": "Where is my order?",
      "message_count": 4,
      "unread_count": 1,
      "last_message_at": "2026-05-24T14:32:00Z",
      "started_at": "2026-05-24T14:28:00Z"
    }
  ],
  "total": 142,
  "limit": 50,
  "offset": 0
}
```

#### POST /admin/api/inbox/conversations/{id}/takeover

```
Request:
{
  "reason": "AI unable to resolve — customer requesting refund"
}

Response: 200
{
  "ok": true,
  "conversation_id": "uuid",
  "previous_status": "active",
  "new_status": "assigned",
  "assigned_to": "operator@merchant.com"
}
```

**Side effects when take-over occurs:**
1. Conversation status → `assigned`, `assigned_to` → current operator
2. Workflow paused (`workflow.pause(db, reason="operator_takeover")`)
3. System message inserted: *"Operator has taken over. AI monitoring paused."*
4. If escalation existed, `escalation.status` → `ASSIGNED`
5. Timeline event recorded: `operator_takeover`

#### POST /admin/api/inbox/messages/send

```
Request:
{
  "conversation_id": "uuid",
  "content": "I can see your order #1234 is delayed. Let me check with the carrier."
}

Response: 201
{
  "id": "uuid",
  "direction": "outgoing",
  "content": "I can see your order #1234 is delayed. Let me check with the carrier.",
  "sender_type": "operator",
  "created_at": "2026-05-24T14:35:00Z"
}
```

### 3.2 Customer Profile API

```
GET    /admin/api/customers/{id}               — Full customer profile
GET    /admin/api/customers/{id}/conversations  — Past conversations
GET    /admin/api/customers/{id}/workflows      — Past workflows
GET    /admin/api/customers/{id}/subscriptions  — Active subscriptions
GET    /admin/api/customers/search?q=           — Search customers
```

### 3.3 Conversation History API

```
GET    /admin/api/conversations/{id}/history    — Unified timeline

Response:
{
  "events": [
    {
      "type": "message",
      "direction": "incoming",
      "content": "Where is my order?",
      "sender_type": "customer",
      "created_at": "..."
    },
    {
      "type": "workflow_transition",
      "from_state": "VALIDATING_IDENTITY",
      "to_state": "RETRIEVING_SHIPMENT",
      "reason": "Order number extracted",
      "created_at": "..."
    },
    {
      "type": "communication",
      "channel": "email",
      "template": "delay_notification",
      "status": "sent",
      "created_at": "..."
    },
    {
      "type": "escalation",
      "reason": "Package lost — auto-escalated",
      "severity": "high",
      "created_at": "..."
    },
    {
      "type": "operator_action",
      "action": "takeover",
      "operator_id": "admin@merchant.com",
      "created_at": "..."
    },
    {
      "type": "message",
      "direction": "outgoing",
      "content": "I've taken over this case.",
      "sender_type": "operator",
      "created_at": "..."
    }
  ]
}
```

---

## 4. UI/UX Design

### 4.1 Layout Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Jeeves sidebar   │              Main Content Area           │
│                   │  ┌──────────────────────────────────────┐│
│  Dashboard        │  │  Inbox                              ││
│  [Inbox] ◄ active │  │  ┌────────────────┬─────────────────┐│
│  Agents           │  │  │ Conversation   │ Customer        ││
│  Knowledge        │  │  │ List (left)    │ Profile (right) ││
│  Connections      │  │  │                │                 ││
│  Settings         │  │  │ • Unassigned 3 │ Name: Alice ... ││
│                   │  │  │ • Alan K. (2)  │ Order: #1234    ││
│                   │  │  │ • Sarah M.(1)  │ Plan: Pro       ││
│                   │  │  │ • ...          │ Risk: Medium    ││
│                   │  │  └────────────────┴─────────────────┘│
│                   │  └──────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Conversation List (Left Panel)

```
┌─────────────────────────────────────┐
│  Inbox                    New: 3    │
│                                     │
│  Filters: [All] [Active] [Waiting]  │
│  [Assigned] [Closed]               │
│                                     │
│  Search...                          │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ ● Alan K.                  14:32│ │
│ │ active · wismo                 │ │
│ │ Where is my order #2113?       │ │
│ │ 📦 Delayed                     │ │
│ ├─────────────────────────────────┤ │
│ │ Sarah M.                  14:15│ │
│ │ handoff_requested · email      │ │
│ │ I want a refund for...         │ │
│ │ ⚠ Escalated                    │ │
│ ├─────────────────────────────────┤ │
│ │ ● Mike R.                  13:50│ │
│ │ assigned to you · widget       │ │
│ │ Thanks for the update!         │ │
│ │ ✔ Resolved                     │ │
│ └─────────────────────────────────┘ │
│                                     │
│  Showing 1-20 of 142     →          │
└─────────────────────────────────────┘
```

**Visual indicators:**
- **Unread dot** (●) — conversation has new messages since operator last viewed
- **Status badge** — `active` (green), `waiting` (amber), `handoff_requested` (red), `assigned` (blue), `closed` (gray)
- **Channel icon** — widget, email, whatsapp
- **Workflow pill** — shows current state if active (e.g. `📦 Delayed`, `⚠ Escalated`, `✅ Resolved`)

### 4.3 Conversation Detail (Center Panel)

```
┌─────────────────────────────────────────────────┐
│  ← Back to inbox   Alan K.         Assign to me │
│  channel: widget · started 14:28                │
│                                                  │
│  ┌─────────────────────────────────────────────┐ │
│  │  Alan K.                 incoming   14:28    │ │
│  │  Where is my order #2113?                   │ │
│  ├─────────────────────────────────────────────┤ │
│  │  Jeeves AI               outgoing   14:28   │ │
│  │  Let me check on order #2113...             │ │
│  ├─────────────────────────────────────────────┤ │
│  │  ⚡ Workflow              system     14:28  │ │
│  │  State: INQUIRY_DETECTED → VALIDATING_IDENTITY││
│  ├─────────────────────────────────────────────┤ │
│  │  ⚡ Workflow              system     14:29  │ │
│  │  State: RETRIEVING_SHIPMENT                 │ │
│  ├─────────────────────────────────────────────┤ │
│  │  Jeeves AI               outgoing   14:30   │ │
│  │  Good news! Your order #2113 is on track    │ │
│  │  and expected to arrive on May 26.          │ │
│  ├─────────────────────────────────────────────┤ │
│  │  ⚠ Escalation             system     14:31  │ │
│  │  Package marked as delayed > 7 days         │ │
│  │  → Auto-escalated (high severity)           │ │
│  │  ─────────────────────────────────          │ │
│  │  [Take over conversation]  [Dismiss]        │ │
│  └─────────────────────────────────────────────┘ │
│                                                  │
│  ┌─────────────────────────────────────────────┐ │
│  │  📝 Internal note (only visible to team)    │ │
│  │  [Add note...]                              │ │
│  └─────────────────────────────────────────────┘ │
│                                                  │
│  ┌─────────────────────────────────────────────┐ │
│  │  Type a message...                    [Send]│ │
│  └─────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

### 4.4 Customer Profile (Right Panel)

```
┌────────────────────────────────────────┐
│  Customer                              │
│                                        │
│  ┌──────────────────────────────────┐  │
│  │  [AJ]                             │  │
│  │  Alan Johnson                     │  │
│  │  alan@example.com                 │  │
│  │  4 conversations · 2 workflows    │  │
│  │  Last seen: 2 min ago             │  │
│  └──────────────────────────────────┘  │
│                                        │
│  ── Active Order ──                    │
│  Order #2113                           │
│  Status: Delayed                       │
│  Expected: May 26                      │
│  Fulfillment: USPS 9400...             │
│  [View in Shopify →]                   │
│                                        │
│  ── Risk ──                            │
│  Risk: Medium                          │
│  Frustration: 65/100 ↑                │
│  Sentiment: Worsening                  │
│                                        │
│  ── Subscription ──                    │
│  Plan: Pro Monthly                     │
│  Status: Active                        │
│  Next renewal: Jun 15                  │
│  MRR: $29.99                          │
│                                        │
│  ── Past Conversations ──              │
│  May 20 — Plan change inquiry     ✓   │
│  Apr 15 — Billing question        ✓   │
│                                        │
│  ── Tags ──                            │
│  [vip] [shopify] [high-value]          │
└────────────────────────────────────────┘
```

### 4.5 Channel Tabs (Inbox Header)

Instead of one monolithic inbox, channel tabs provide quick filtering:

```
┌──────────────────────────────────────────────────────────────┐
│  [All] [Widget ● 3] [Email ● 1] [WhatsApp] [Closed (142)]  │
│                                                              │
│  ● Unassigned (3)    ● Assigned to me (1)    All (5)        │
└──────────────────────────────────────────────────────────────┘
```

### 4.6 Real-time Updates

The inbox needs to feel live. Two approaches:

**Phase 1 — Polling (MVP):**
```
setInterval(async () => {
  const data = await api('/admin/api/inbox/conversations?status=active,waiting,handoff_requested,assigned&since=' + lastFetch);
  if (data.conversations.length > 0) {
    updateConversationList(data.conversations);
    playNotificationSound(data.conversations.filter(c => c.unread_count > 0));
  }
}, 5000);  // Poll every 5 seconds
```

**Phase 2 — Server-Sent Events (post-MVP):**
```
GET /admin/api/inbox/events
→ SSE stream: new_message, conversation_assigned, workflow_state_changed, escalation
```

---

## 5. Operator Handoff Flow

### 5.1 State Machine

```
                  ┌─────────────┐
                  │   ACTIVE    │ ← AI is handling conversation
                  └──────┬──────┘
                         │ AI cannot resolve / policy triggers escalation
                         ▼
               ┌──────────────────┐
               │ HANDOFF_REQUESTED │ ← Operator sees this in inbox
               └──────────────────┘
                         │
                    ┌────┴────┐
                    │         │
                    ▼         ▼
              ┌────────┐ ┌────────┐
              │ASSIGNED│ │ CLOSED │ ← AI auto-resolved / customer went away
              └───┬────┘ └────────┘
                  │
          ┌───────┴────────┐
          │                │
          ▼                ▼
    ┌──────────┐    ┌──────────┐
    │  CLOSED  │    │  ACTIVE  │ ← Return to AI (if operator releases)
    └──────────┘    └──────────┘
```

### 5.2 Takeover Triggers

| Trigger | Source | Conversation becomes |
|---------|--------|---------------------|
| AI confidence < 0.3 | AI classifier | `HANDOFF_REQUESTED` |
| Policy escalation | Policy engine (e.g. lost package) | `HANDOFF_REQUESTED` |
| Operator clicks "Take over" | Operator UI | `ASSIGNED` |
| Customer requests human | Customer message | `HANDOFF_REQUESTED` |
| SLA breached (24h no resolution) | Background scheduler | `HANDOFF_REQUESTED` |

### 5.3 Handoff Context Package

When handoff occurs, the following context is packaged for the operator:

```json
{
  "conversation_id": "uuid",
  "customer": {
    "display_name": "Alan Johnson",
    "email": "alan@example.com",
    "risk_level": "medium",
    "frustration_score": 65
  },
  "workflow": {
    "type": "wismo",
    "state": "CLASSIFYING_RISK",
    "order_id": "#2113",
    "tracking_status": "delayed",
    "delay_days": 8
  },
  "escalation": {
    "reason": "Package delayed > 7 days",
    "severity": "high",
    "sla_remaining": "16 hours"
  },
  "ai_summary": "Customer asked about order #2113. Tracking shows package delayed for 8 days. Sent one notification on May 23. Customer has not responded to last message.",
  "last_3_messages": [
    {"from": "customer", "content": "Where is my order #2113?"},
    {"from": "ai", "content": "Let me check on that for you..."},
    {"from": "ai", "content": "Your package is delayed. I've escalated this to our team."}
  ]
}
```

### 5.4 Return to AI

After an operator resolves the issue, they can return the conversation to AI:

```
POST /admin/api/inbox/conversations/{id}/return-to-ai
```

This:
1. Sets conversation status → `ACTIVE`
2. Resumes workflow (`workflow.resume(db)`)
3. Adds system message: *"Conversation returned to AI agent."*

---

## 6. Implementation Plan

### Phase 1 — Foundation (Week 1-2)

| Step | Files | Description |
|------|-------|-------------|
| 1.1 | `api/app/models.py` | Add `Conversation`, `Message`, `OperatorNote` models |
| 1.2 | Alembic migration | Create new tables |
| 1.3 | `api/app/admin/inbox.py` | Scaffold the module, define Pydantic schemas |
| 1.4 | `api/app/admin/router.py` | Register inbox routes |

### Phase 2 — Write Path (Week 2-3)

| Step | Files | Description |
|------|-------|-------------|
| 2.1 | `api/app/channels/widget.py` | Modify `POST /widget/chat` to write to `Conversation` + `Message` |
| 2.2 | `api/app/routes_chat.py` | Modify `POST /chat` similarly |
| 2.3 | `api/app/core/workflows/wismo.py` | Modify `_send_notification` to write outgoing to `Message` |
| 2.4 | `api/app/core/execution/` | Ensure all action audit trails update `Message` for system events |

### Phase 3 — Inbox UI (Week 3-4)

| Step | Files | Description |
|------|-------|-------------|
| 3.1 | `api/app/admin/inbox.py` | Implement all inbox API endpoints |
| 3.2 | `api/app/templates/inbox.html` | Main inbox page (extends base.html) |
| 3.3 | Sidebar nav update | Add "Inbox" link to base.html sidebar |
| 3.4 | Conversation detail component | JS-powered message list with infinite scroll |
| 3.5 | Customer profile component | Right panel with customer data |
| 3.6 | Operator send message | Chat input at bottom of conversation |

### Phase 4 — Handoff (Week 4-5)

| Step | Files | Description |
|------|-------|-------------|
| 4.1 | `api/app/admin/inbox.py` | Implement `POST /takeover` and `POST /return-to-ai` |
| 4.2 | `api/app/core/workflows/runtime.py` | Add `pause()`, `resume()` methods with operator context |
| 4.3 | Workflow integration | Modify workflow to handle operator_takeover event |
| 4.4 | Escalation integration | Link escalation → handoff_requested automatically |
| 4.5 | UI: handoff button | "Take over" button in escalation cards and conversation header |

### Phase 5 — Polish (Week 5-6)

| Step | Description |
|------|-------------|
| 5.1 | Real-time polling with unread indicators |
| 5.2 | Customer search in profile sidebar |
| 5.3 | Keyboard shortcuts (Escape to close, Enter to send, etc.) |
| 5.4 | Notification sound for new handoff requests |
| 5.5 | Dual-write to ChatLog for backward compatibility |

---

## 7. Key Design Decisions

### 7.1 Why a separate `Conversation` model instead of reusing ChatLog?

`ChatLog` was designed as an audit log (one row = one customer query + one bot response).
It conflates two messages into one row and has no concept of status, assignment, or lifecycle.
A `Conversation` + `Message` model gives us proper normalization.

### 7.2 Why `user_id` as text and not a FK to Customer?

Customer creation is lazy (happens on first contact). The `user_id` is the canonical external
identifier (shopify_customer_id, email, etc.). The `customer_id` FK is set when the Customer
record exists. This avoids race conditions on customer creation during high-throughput message
ingestion.

### 7.3 Why pause the workflow during operator takeover?

If the workflow continues running while the operator is handling the conversation, it could
send conflicting responses (workflow sends "Let me check" while operator is typing).
Pausing prevents this. The workflow resumes when the operator returns control to AI.

### 7.4 Why polling over WebSockets/SSE for Phase 1?

The existing infrastructure has no WebSocket support. Polling is simpler to implement
and debug. SSE can be added in Phase 2 for lower latency. The 5-second poll interval
matches Crisp's effective latency.

### 7.5 Why not use the existing `session_id` on ChatLog?

`ChatLog.session_id` is a random UUID generated per widget interaction — it does not
persist across customer visits. The new `Conversation` model groups messages by
`tenant_id` + `user_id` with a configurable inactivity timeout (24h default) before
creating a new conversation.

---

## 8. Open Questions

1. **Inactivity timeout**: After how long without messages should a conversation auto-close? 24h? 72h?
2. **Operator model**: MVP uses tenant email as operator identity. When should we introduce a proper Agent model with roles?
3. **Multiple operators per tenant**: MVP is single-operator. How does the design scale to team inbox?
4. **Canned responses**: Should operator have saved reply templates in MVP?
5. **CSAT survey**: Send after conversation close? In-widget or via email?
