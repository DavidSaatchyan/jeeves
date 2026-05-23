# WISMO MVP Implementation Plan

## Overview

WISMO (Where Is My Order) is an autonomous agent that intercepts order inquiries from Shopify, resolves tracking status from carrier data, and proactively communicates delivery updates to customers via widget or email.

## Architecture: Two Entry Points

```
┌──────────────────────────┐     ┌─────────────────────────────┐
│   Shopify Webhook         │     │   Widget Chat               │
│   (fulfillments/create,   │     │   (customer types message)  │
│    tracking_updated)      │     │                             │
└─────────┬────────────────┘     └──────────┬──────────────────┘
          │                                  │
          ▼                                  ▼
   CanonicalEvent                      Intent Classifier
   (fulfillment_created,              (LLM: wismo / kb_query / general)
    tracking_updated)                       │
          │                           ┌─────┼──────┐
          │                           │     │      │
          │                          wismo  kb    general
          │                           │     │      │
          └──────┬────────────────────┘     │      │
                 │                    RAG search  LLM
                 ▼                    + response  greeting
          WismoWorkflow
          ┌──────────────────┐
          │ VALIDATING_ID    │
          │ RETRIEVING_DATA  │
          │ CLASSIFYING_RISK │
          │ SENDING_RESPONSE │
          │ RESOLVED / LOST  │
          └──────────────────┘
```

**Key insight**: Intent classification happens BEFORE RAG search. This prevents wasting LLM tokens on RAG when the query is clearly an order-tracking request that needs real Shopify API data.

---

## State Machine

```
INQUIRY_DETECTED → VALIDATING_IDENTITY → RETRIEVING_SHIPMENT → CLASSIFYING_RISK → RESPONSE_SENT → RESOLVED
                  → VALIDATING_IDENTITY → WAITING_ORDER_SELECTION → RETRIEVING_SHIPMENT ...
                                                                  → ESCALATED
                  → ESCALATED (customer/order not found)
                                                                                      → RESOLVED (on-track)
                                                                                      → LOST (package lost)
                                                                                      → ESCALATED (unresolvable)
```

| State | Description |
|-------|-------------|
| `INQUIRY_DETECTED` | Order inquiry event received (webhook or chat message) |
| `VALIDATING_IDENTITY` | Identify customer + parse/search order. Branches: single order → proceed, no order → ESCALATED, multiple → WAITING |
| `WAITING_ORDER_SELECTION` | Asked customer which order, waiting for reply. On reply: parse order# → proceed or ask again |
| `RETRIEVING_SHIPMENT` | Fetch order + fulfillment data from Shopify API |
| `CLASSIFYING_RISK` | LLM classifies tracking status: on-track / delayed / lost |
| `RESPONSE_SENT` | Proactive update delivered to customer |
| `RESOLVED` | Terminal — inquiry resolved successfully |
| `LOST` | Terminal — package lost, escalation needed |
| `ESCALATED` | Terminal — handoff to human support |

---

## Trigger Events → WISMO Mapping

| Event | Source | Action |
|-------|--------|--------|
| `fulfillment_created` | Shopify webhook | Create/update WISMO workflow, classify tracking, notify if delayed |
| `tracking_updated` | Shopify webhook | Same as above |
| `order_created` | Shopify webhook | Optionally create WISMO workflow in monitoring state |
| `intent: wismo` | Widget chat (after intent classification) | Create/update WISMO workflow, fetch real data, respond |

---

## Phase 1: Core Workflow Engine Fixes

### 1.1 `core/workflows/wismo.py` (NEW)
- `WismoWorkflow(Workflow)` subclass
- `handle_event()` dispatches by event type:
  - `fulfillment_created` / `tracking_updated` → full cycle
  - `intent: wismo` (from chat) → fetch + respond
- Helper methods: `_validate_identity()`, `_retrieve_shipment()`, `_classify_risk()`, `_send_response()`
- ALL AI calls have deterministic fallbacks

### 1.2 `core/workflows/transitions.py` (MODIFY)
- Replace `return False` with WISMO transition table
- `WISMO_TRANSITIONS: dict[str, list[str]]`
- `validate_transition()` checks workflow_type and looks up table

### 1.3 `core/workflows/registry.py` (MODIFY)
- Remove dead code (lines 19-52 — orphaned insert logic)
- Add `route_event()` function:
  ```
  WISMO_EVENTS = {"fulfillment_created", "tracking_updated", "order_created", "intent:wismo"}
  route_event() → maps event_type → workflow_type → creates/loads workflow → handle_event()
  ```
- Lock-based dedup: one active WISMO workflow per (tenant_id, customer_id, order_id)

### 1.4 `core/workflows/__init__.py` (MODIFY)
- Import and register WISMO workflow on startup

---

## Phase 1.5: Intent Classification (NEW — critical fix to original plan)

### 1.5 `core/ai/intent_classifier.py` (NEW)
- `classify_intent(message: str, tenant_id: UUID) -> str`
- LLM classifies into: `"wismo"`, `"kb_query"`, `"general"`
- Prompt:
  ```
  Classify this customer message into one of:
  - wismo: customer asking about order status, tracking, delivery time, "where is my order"
  - kb_query: customer asking for information (policies, FAQ, product info)
  - general: greeting, thanks, small talk, unclear

  Message: <text>
  Classification:
  ```
- Fallback: `"kb_query"` (safe — will RAG search, and if nothing found, says "don't know")
- Only called for widget chat (not for webhook events)

### Integration in `channels/widget.py` (MODIFY)
- After moderation, BEFORE RAG search:
  ```
  intent = await classify_intent(body.message, tenant.id)
  if intent == "wismo":
      → create/load WismoWorkflow
      → handle_event() with event_type "intent:wismo"
      → return response from WISMO (real Shopify data)
  elif intent == "kb_query":
      → current RAG + LLM flow
  else:  # general
      → simple LLM greeting response (no RAG)
  ```

---

## Phase 2: Shopify ↔ WISMO Integration

### 2.1 `core/workflows/wismo_service.py` (NEW)
- `get_or_create_wismo(db, tenant_id, customer_id, order_id) → WismoWorkflow`
- `fetch_order(tenant_id, order_id, db) → dict` (calls `shopify.actions.fetch_order()`)
- `fetch_fulfillments(tenant_id, order_id, db) → list[dict]` (calls `shopify.actions.fetch_fulfillments()`)
- `find_order_by_customer_and_query(tenant_id, customer_id, query, db) → order_id | None`
  - Used when customer asks "where is my order" without order number
  - Searches recent orders for the customer, matches by date/product

### 2.2 `integrations/webhooks.py` (VERIFY)
- Already normalizes Shopify webhooks → CanonicalEvent → dispatch_event()
- Just needs `route_event()` to exist (Phase 1.3)

---

## Phase 3: AI Classification & Response

### 3.1 `core/ai/wismo_classifier.py` (NEW)
- `classify_tracking_status(fulfillments: list[dict], order: dict) -> dict`
  - Input: fulfillment data (carrier, tracking#, status, estimated_delivery)
  - Output: `{"status": "on_track"|"delayed"|"lost", "confidence": int, "reason": "...", "estimated_delivery": "...", "carrier_status": "..."}`
- Uses GPT-4o-mini with `temperature=0.1`
- Fallback: `{"status": "on_track", "confidence": 0, "reason": "LLM unavailable"}` (silence is safer than false alarm)

### 3.2 `core/ai/wismo_responder.py` (NEW)
- `generate_wismo_widget_response(classification: dict, order: dict, customer: dict) -> str`
  - Widget: short conversational message (1-2 sentences)
  - E.g.: "Good news! Your order #1234 is on track and expected by May 28."
- `generate_wismo_email(classification: dict, order: dict, customer: dict) -> dict`
  - Email: full message with order details + tracking link
- Fallback: static template for each status type

---

## Phase 4: Communication Templates

### 4.1 `core/communications/templates.py` (MODIFY)
- Add WISMO templates alongside existing ones:
  - `render_tracking_update(context)` — on-track notification
  - `render_delay_notification(context)` — delayed delivery
  - `render_delivery_confirmation(context)` — delivered successfully
  - `render_lost_package(context)` — package lost, escalation offered

### 4.2 `core/communications/service.py` (MODIFY)
- Register WISMO templates in the `templates` dict
- Wire up `send_communication()` for WISMO channels

---

## Phase 5: Admin UI

### 5.1 `admin.py` — Funnel stages (MODIFY)
- Add WISMO-specific funnel:
  ```
  "detected": {"states": ["INQUIRY_DETECTED", "VALIDATING_IDENTITY"]}
  "identified": {"states": ["RETRIEVING_SHIPMENT", "CLASSIFYING_RISK"]}
  "informed": {"states": ["RESPONSE_SENT"]}
  "resolved": {"states": ["RESOLVED"]}
  "lost": {"states": ["LOST", "ESCALATED"]}
  ```

### 5.2 Feed icons (VERIFY)
- JS already handles WISMO states — just need backend to return correct events

---

## Phase 6: Tests

### 6.1 Unit tests: `tests/test_wismo.py` (NEW)
- Test state transitions (valid + invalid)
- Test classification fallback
- Test response generation fallback
- Test intent classification

### 6.2 Integration
- Webhook → workflow creation → transition → response

---

## File Manifest

| Action | File | Phase |
|--------|------|-------|
| CREATE | `core/workflows/wismo.py` | 1 |
| MODIFY | `core/workflows/transitions.py` | 1 |
| MODIFY | `core/workflows/registry.py` | 1 |
| MODIFY | `core/workflows/__init__.py` | 1 |
| CREATE | `core/ai/intent_classifier.py` | 1.5 |
| MODIFY | `channels/widget.py` | 1.5 |
| CREATE | `core/workflows/wismo_service.py` | 2 |
| CREATE | `core/ai/wismo_classifier.py` | 3 |
| CREATE | `core/ai/wismo_responder.py` | 3 |
| MODIFY | `core/communications/templates.py` | 4 |
| MODIFY | `core/communications/service.py` | 4 |
| MODIFY | `admin.py` | 5 |
| CREATE | `tests/test_wismo.py` | 6 |

## Correction from Original Plan

**Old (wrong)**: RAG search → if nothing found → create WISMO workflow.

**New (correct)**: Intent classifier → if `wismo` → trigger WISMO workflow (fetches real Shopify data). If `kb_query` → RAG search + LLM response. If `general` → simple LLM greeting.

WISMO is NOT a fallback for when RAG fails. WISMO is a separate path triggered by intent classification — it uses live Shopify API data, not static KB documents.

---

## Order Lookup Flow (How client → order matching works)

### Widget Chat: 3 scenarios

**Scenario A — Customer specifies order number in message**
```
"where is my order #5678"
  → parse_order_number() → "5678"
  → fetch_order(tenant, "5678") → order found ✅
  → proceed to RETRIEVING_SHIPMENT
```

**Scenario B — Customer has exactly 1 recent order**
```
"where is my order"
  → parse_order_number() → None
  → find_orders_by_customer() → [order] (1 result)
  → use that order → proceed to RETRIEVING_SHIPMENT ✅
```

**Scenario C — Customer has 2+ recent orders, no number given**
```
"where is my order"
  → parse_order_number() → None
  → find_orders_by_customer() → [orderA, orderB, orderC] (3 results)
  → WAITING_ORDER_SELECTION
  → ChatLog: "I found several orders... 1. #1001 (shipped) 2. #1002 (unfulfilled)..."
  
Customer replies: "#1002"
  → same workflow loaded (WAITING_ORDER_SELECTION state)
  → parse_order_number("#1002") → "1002"
  → fetch_order → found → update workflow.order_id → RETRIEVING_SHIPMENT ✅
```

**Escalation cases:**
- No orders found → ESCALATED
- Order# specified but not found in Shopify → ESCALATED
- Customer in WAITING_ORDER_SELECTION gives invalid number → stay in state, ask again

### Shopify Webhook: direct link
Webhook payload always includes both `customer_id` and `order_id`:
```json
{
  "customer_id": "123",
  "order_id": "456"
}
```
→ `route_event()` finds or creates workflow WITH order_id
→ Dedup by `(tenant_id, customer_id, order_id)` — one workflow per (customer, order)

## Dependency Order

```
Phase 1 (Core engine)
    ↓
Phase 1.5 (Intent classification) — unblocks widget → WISMO path
    ↓
Phase 2 (Shopify service)
    ↓
Phase 3 (AI classification + response)
    ↓
Phase 4 (Templates)
    ↓
Phase 5 (Admin UI)
    ↓
Phase 6 (Tests)
```
