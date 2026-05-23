# WISMO: Policy Engine + Conversation Memory

## Part 1: Policy Engine → WISMO

### What
Add `wismo_policy` JSONB column to `PolicySet`. Connect `PolicyEngine` to `WismoWorkflow` so all operational decisions go through policies.

### Why
- Merchants need per-tenant control over auto-notify, escalation, channels
- Currently all behaviour is hardcoded in wismo.py
- Without policies: every merchant gets same behaviour, admin has no UI control

### Changes

#### 1. `models.py` — PolicySet
```python
wismo_policy = Column(JSONB, default=dict)
```

Default value (loaded when `wismo_policy` is empty or None):
```yaml
auto_notify: true              # auto-send notification when delayed/lost
auto_notify_threshold: "delayed" # min severity to notify: on_track | delayed | lost
notification_channels: ["widget"]  # allowed channels for proactive messages
escalation_delay_days: 7       # days delayed before auto-escalation to admin
auto_escalate_lost: true       # lost → immediate escalation
max_silent_tracking_days: 14   # no tracking update → escalation
```

#### 2. `core/policies/engine.py` — PolicyEngine
- Add `_DEFAULT_WISMO` dict
- Add `_evaluate_wismo(context)` method
- Accept `"wismo"` in `evaluate()` dispatch

All WISMO defaults are returned as-is (no complex evaluation needed yet — just config lookup).

```python
def _evaluate_wismo(self, context: dict) -> dict:
    policies = self._policy.get("wismo", _DEFAULT_WISMO)
    return policies  # returns full snapshot
```

#### 3. `core/workflows/wismo.py` — WismoWorkflow
| Location | Change |
|----------|--------|
| `__init__` | Load `self.wismo_policy = PolicyEngine(tenant_id, db).evaluate("wismo", {})` |
| `_fire_outgoing_webhooks` (pre-send) | Skip send if `auto_notify == False` |
| `_classify_and_respond` (delayed branch) | If `delay_days >= escalation_delay_days` → `transition_to(ESCALATED)` |
| `_classify_and_respond` (lost branch) | If `auto_escalate_lost` → `transition_to(ESCALATED)` |
| Tracking refresh | Check `max_silent_tracking_days` in `RETRIEVING_SHIPMENT` |
| `_send_notification` | Filter ch by `notification_channels` |

#### 4. Alembic
- New migration: `add_wismo_policy_to_policyset`
- `ALTER TABLE policy_sets ADD COLUMN wismo_policy JSONB DEFAULT '{}'`

#### 5. Admin UI (`agents.html`)
- Policy config section already exists
- Add WISMO-specific fields to the policy form (toggled when editing wismo policies)

---

## Part 2: Conversation Memory

### What
Pass last N ChatLog messages as context to: intent classifier, WISMO workflow, KB RAG response generator.

Current state: every widget message is processed stateless. Intent classifier sees only `message`, not the conversation history.

### Why
- `WAITING_ORDER_SELECTION` → client answers `#1002` → intent classifies as `general` (broken flow)
- KB follow-ups lose context (`"what about electronics"` after `"return policy"`)
- Proactive notifications leave no trace for next message interpretation

### Changes

#### 1. `core/memory.py` — new file
```python
def get_conversation_history(
    tenant_id: str, customer_id: str,
    limit: int = 15,
    max_age_hours: int = 24,
    db: Session | None = None,
) -> list[dict]:
    """Fetch recent ChatLog entries formatted for LLM context."""
    ...
    # Returns: [{"role": "customer"/"assistant", "content": "..."}, ...]
```

- Query `ChatLog` where `tenant_id == tenant_id AND customer_id == customer_id`
- Order by `created_at DESC`, limit 15
- Filter: only messages from last 24 hours
- Format: `{"role": "customer" | "assistant", "content": message}`
- Reverse to chronological order before returning

#### 2. `core/ai/intent_classifier.py`
- Add `history: list[dict] = field(default_factory=list)` parameter
- Include history in system prompt:
```
Conversation history (newest last):
- customer: where is my order
- assistant: You have orders #1002 and #1003. Which one?
- customer: #1002

Current message: "#1002"
```

#### 3. `channels/widget.py`
- Before calling `classify_intent()`: load conversation history
- Pass `history` to:
  - `intent_classifier.classify(message, history)` → better intent detection
  - `wismo_workflow.route_event(event, history)` → WISMO sees context
  - KB query (included in RAG prompt) → LLM sees conversation context

#### 4. `core/workflows/wismo.py`
- In `WAITING_ORDER_SELECTION`: if last assistant message was asking for order selection, use `history` to detect client's order choice without re-running intent classifier
- When generating response: include `history` context for better replies

#### 5. Index on ChatLog (optional)
- Add composite index: `(tenant_id, customer_id, created_at)` if not exists
- Ensures `get_conversation_history()` is fast at scale

### Retention
| Layer | Retention | Rationale |
|-------|-----------|-----------|
| ChatLog (DB) | Indefinite | Audit trail, admin history view |
| LLM context | Last 15 msgs OR last 24h (whichever fewer) | Token budget, relevance |
| Future cleanup job | TTL 90 days | Optional, not part of this PR |

---

## Order of Implementation

1. **Policy Engine** (smaller, self-contained, no cross-module changes)
   1. models.py — add `wismo_policy` column
   2. Alembic migration
   3. engine.py — add WISMO policy type
   4. wismo.py — integrate policy checks
   5. `python -c "from app.main import app"` — verify imports

2. **Conversation Memory** (touches more files)
   1. `core/memory.py` — `get_conversation_history()`
   2. intent_classifier.py — add `history` parameter
   3. widget.py — load + pass history
   4. wismo.py — use history in WAITING_ORDER_SELECTION
   5. `python -c "from app.main import app"` — verify imports
   6. Run 287 tests

---

## Dependency Direction
```
models.py  ←  core/policies/engine.py  ←  core/workflows/wismo.py
                                        ←  channels/widget.py

core/memory.py  →  core/ai/intent_classifier.py
core/memory.py  →  channels/widget.py
core/memory.py  →  core/workflows/wismo.py
```

No circular imports. No dependency direction violations (core ← channels, not core → channels).
