# WISMO: Implementation Plan — Policy Engine + Conversation Memory

## Overview

Two independent features, done sequentially:

| # | Feature | Files changed | Complexity |
|---|---------|---------------|------------|
| 1 | Policy Engine → WISMO | 4 files | Low (new policy type, config lookup) |
| 2 | Conversation Memory | 4 files | Medium (cross-module wiring) |

---

## Part 1: Policy Engine → WISMO

### Goal
WISMO reads per-tenant `wismo_policy` from `PolicySet` and uses it to decide: when to notify, which channels, when to escalate.

### Files

#### 1a. `api/app/models.py` — add column

**Location**: `PolicySet` class (line 407), after `approval_policy` (line 416)

**Change**:
```python
wismo_policy = Column(JSONB, default=dict)
```

Also add to `created_at` / `updated_at` if missing (currently has them).

**Verify**: `python -c "from app.models import PolicySet; print(hasattr(PolicySet, 'wismo_policy'))"` → `True`

---

#### 1b. `api/alembic/versions/<new>_add_wismo_policy_to_policyset.py` — migration

**Change**: new migration file via `alembic revision --autogenerate` or manual:

```python
"""add wismo_policy to policy_sets

Revision ID: xyz
Revises: bc8ca329a4fa
Create Date: 2026-05-23
"""
from alembic import op
import sqlalchemy as sa

revision = "new_id"
down_revision = "bc8ca329a4fa"

def upgrade():
    op.add_column("policy_sets", sa.Column("wismo_policy", sa.JSON(), nullable=True))

def downgrade():
    op.drop_column("policy_sets", "wismo_policy")
```

**Verify**: `alembic upgrade head` succeeds; `alembic downgrade -1` rolls back.

---

#### 1c. `api/app/core/policies/engine.py` — add WISMO policy type

**Location**: after `_DEFAULT_APPROVAL` block (line 28) and `_evaluate_approval` method.

**New defaults** (after line 28):
```python
_DEFAULT_WISMO = {
    "auto_notify": True,
    "auto_notify_threshold": "delayed",  # "on_track" | "delayed" | "lost"
    "notification_channels": ["widget"],  # ["widget"], ["email"], ["widget", "email"]
    "escalation_delay_days": 7,
    "auto_escalate_lost": True,
    "max_silent_tracking_days": 14,
    "max_notifications_per_workflow": 3,
}
```

**New dispatch** in `evaluate()` (line 61, after `approval` branch):
```python
if policy_type == "wismo":
    return self._evaluate_wismo(context)
```

**New method** (after `_evaluate_approval`, before `get_policy_snapshot`):
```python
def _evaluate_wismo(self, context: dict[str, Any]) -> dict[str, Any]:
    policies = self._policy.get("wismo", _DEFAULT_WISMO)
    return {
        "allowed": True,
        "policy": policies,
        "auto_notify": policies.get("auto_notify", True),
        "auto_notify_threshold": policies.get("auto_notify_threshold", "delayed"),
        "notification_channels": policies.get("notification_channels", ["widget"]),
        "escalation_delay_days": policies.get("escalation_delay_days", 7),
        "auto_escalate_lost": policies.get("auto_escalate_lost", True),
        "max_silent_tracking_days": policies.get("max_silent_tracking_days", 14),
        "max_notifications_per_workflow": policies.get("max_notifications_per_workflow", 3),
    }
```

**Update `get_policy_snapshot()`** (line 133): add `"wismo": self._policy.get("wismo", _DEFAULT_WISMO)` to returned dict.

**Verify**: `python -c "from app.core.policies.engine import PolicyEngine; p=PolicyEngine('test'); r=p.evaluate('wismo', {}); print(r['auto_notify'])"` → `True`

---

#### 1d. `api/app/core/workflows/wismo.py` — integrate policy checks

**Import** (top of file, after `from ..events.schemas import CanonicalEvent`):
```python
from ..policies.engine import PolicyEngine
```

**`__init__`** — currently WismoWorkflow inherits from Workflow. Add:
```python
async def _load_policy(self, db: Session) -> None:
    self.wismo_policy = PolicyEngine(
        tenant_id=str(self.tenant_id), db=db
    ).evaluate("wismo", {})
```

Call in `handle_event` (before branching, after `self.current_state` is available):
```python
if not hasattr(self, "wismo_policy") or not self.wismo_policy:
    self.wismo_policy = PolicyEngine(tenant_id=str(self.tenant_id), db=db).evaluate("wismo", {})
```

Actually, simpler: add to the start of `handle_event`:
```python
async def handle_event(self, event: CanonicalEvent, db: Session) -> None:
    if not hasattr(self, "_policy_loaded"):
        self.wismo_policy = PolicyEngine(tenant_id=str(self.tenant_id), db=db).evaluate("wismo", {})
        self._policy_loaded = True
    ...
```

**Integration points in `_classify_and_respond`** (line 186):

Before `transition("CLASSIFYING_RISK", ...)`:
```python
# Policy check: silence on_track notifications if threshold is "delayed" or lower
if status == "on_track" and self.wismo_policy["auto_notify_threshold"] != "on_track":
    # don't notify for on_track — silence is safe
    await self.transition("RESOLVED", event, db, reason="on_track_silent_per_policy")
    await self._resolve_if_terminal(db)
    return
```

After tracking classification:
```python
# Policy check: escalate if delayed too long
if status == "delayed":
    delay_days = classification.get("delay_days", 0)
    if delay_days >= self.wismo_policy["escalation_delay_days"]:
        await self.transition("ESCALATED", event, db, reason=f"delayed_{delay_days}d_exceeds_policy")
        await self._send_notification(event, db, order, classification)
        await self._resolve_if_terminal(db)
        return

if status == "lost" and self.wismo_policy["auto_escalate_lost"]:
    await self.transition("ESCALATED", event, db, reason="lost_auto_escalated")
    await self._send_notification(event, db, order, classification)
    await self._resolve_if_terminal(db)
    return
```

**Integration in `_send_notification`** (line 213):

Check `auto_notify` flag:
```python
if not self.wismo_policy["auto_notify"]:
    logger.info("WISMO %s: auto_notify disabled by policy, skipping notification", self.workflow_id)
    return
```

Filter channels by policy:
```python
allowed_channels = self.wismo_policy["notification_channels"]
# widget channel always
if "widget" in allowed_channels:
    ...send widget...

# email channel only if policy allows
if "email" in allowed_channels and context.get("email"):
    ...send email...
```

Check `max_notifications_per_workflow` — count existing outgoing ChatLog entries for this workflow:
```python
existing_notifications = db.query(...ChatLog).filter(
    ChatLog.tenant_id == self.tenant_id,
    ChatLog.user_id == customer_id,
    ChatLog.direction == "outgoing",
    ChatLog.created_at >= ...  # since workflow start
).count()
if existing_notifications >= self.wismo_policy["max_notifications_per_workflow"]:
    logger.info("WISMO %s: max notifications reached", self.workflow_id)
    return
```

**Verify**: `python -c "from app.main import app"` — imports resolve; run 287 tests.

---

### Order of implementation (Part 1)

1. `models.py` — add `wismo_policy` column
2. `engine.py` — add `_DEFAULT_WISMO`, `_evaluate_wismo()`, update `get_policy_snapshot()`
3. `wismo.py` — integrate policy checks
4. Alembic migration — new revision
5. Verify: import + 287 tests

---

## Part 2: Conversation Memory

### Goal
Each widget message includes last N ChatLog entries as LLM context. Intent classifier, WISMO workflow, and KB RAG all see the conversation history.

### Files

#### 2a. `api/app/core/memory.py` — NEW file

```python
"""Conversation memory — fetches recent ChatLog entries for LLM context."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import ChatLog

_MAX_MESSAGES = 15
_MAX_AGE_HOURS = 24


def get_conversation_history(
    tenant_id: str,
    customer_id: str,
    limit: int = _MAX_MESSAGES,
    max_age_hours: int = _MAX_AGE_HOURS,
    db: Session | None = None,
) -> list[dict]:
    """Return recent ChatLog entries for this customer, newest last.

    Returns list of {"role": "customer"|"assistant", "content": str}
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        rows = (
            db.query(ChatLog)
            .filter(
                ChatLog.tenant_id == tenant_id,
                ChatLog.user_id == customer_id,
                ChatLog.created_at >= cutoff,
            )
            .order_by(desc(ChatLog.created_at))
            .limit(limit)
            .all()
        )
    finally:
        if close_db:
            db.close()

    # Reverse to chronological order (oldest first for LLM)
    history = []
    for row in reversed(rows):
        if row.direction == "incoming" and row.message:
            history.append({"role": "customer", "content": row.message})
        elif row.direction == "outgoing" and row.response:
            history.append({"role": "assistant", "content": row.response})

    return history
```

**Verify**: `python -c "from app.core.memory import get_conversation_history; print(get_conversation_history('x', 'y'))"` → `[]` (no error)

---

#### 2b. `api/app/core/ai/intent_classifier.py` — add history context

**New signature**:
```python
async def classify_intent(message: str, tenant_id: str, history: list[dict] | None = None) -> str:
```

**Change**: inject history into prompt, before the message:

```python
prompt_parts = [
    "Classify this customer message into exactly one category:",
    "- wismo: ...",
    "- kb_query: ...",
    "- general: ...",
]

if history:
    prompt_parts.append("\nConversation history (newest last):")
    for entry in history:
        role = entry.get("role", "customer")
        content = entry.get("content", "")
        prompt_parts.append(f"- {role}: {content[:200]}")

prompt_parts.append(f"\nCurrent message: {message}")
prompt_parts.append("Category:")
```

**Fallback unchanged** — LLM failure still returns `"kb_query"`.

**Verify**: `python -c "from app.core.ai.intent_classifier import classify_intent; import asyncio; asyncio.run(classify_intent('test', 'tenant', []))"` (no crash)

---

#### 2c. `api/app/channels/widget.py` — load + pass history

**In `widget_chat`** (line 67):

After `log = ChatLog(...)` and before `classify_intent` (line 101):

```python
# Load conversation history for context
from ..core.memory import get_conversation_history
history = get_conversation_history(
    tenant_id=str(tenant.id),
    customer_id=body.user_id,
    db=db,
)
```

Then pass to `classify_intent` (line 102):
```python
intent = await classify_intent(body.message, str(tenant.id), history=history)
```

In the `"wismo"` branch (line 104), pass history in the CanonicalEvent payload:
```python
ev = CanonicalEvent(
    ...
    payload={
        "customer_id": body.user_id,
        "message": body.message,
        "history": history,          # NEW
    },
)
```

In the `"general"` branch (line 143), pass history to `_simple_llm_response` (will need to check if it accepts context):
```python
result = await _simple_llm_response(tenant.id, body.message, conversation_history=history)
```

In the `kb_query` branch (line 146), include history in the system prompt:
```python
system = (
    "You are a support agent. Answer the user's question based ONLY on the context below. ..."
    + (f"\n\nConversation history:\n{format_history(history)}" if history else "")
    + "\n\nContext:\n" + context
)
```

Add helper:
```python
def _format_history(history: list[dict]) -> str:
    return "\n".join(f"{e['role']}: {e['content']}" for e in history)
```

---

#### 2d. `api/app/core/workflows/wismo.py` — use history

**In `_handle_chat_inquiry`** (line 31):

If `WAITING_ORDER_SELECTION` + history passed in event payload:
- Instead of only checking `parse_order_number(message)`, also scan history for last assistant message
- If last assistant message was "which order?" and customer replied with a number → use it

```python
async def _handle_order_selection(self, event: CanonicalEvent, db: Session) -> None:
    payload = event.payload or {}
    message = payload.get("message", "")
    history = payload.get("history", [])
    ...
```

Also: when generating response, include context from history for better LLM generation (in `generate_wismo_widget_response`).

---

#### 2e. (Optional) Index on ChatLog

Check if composite index `(tenant_id, user_id, created_at)` exists. If not, add via Alembic:

```python
op.create_index(
    "ix_chat_logs_tenant_user_created",
    "chat_logs",
    ["tenant_id", "user_id", "created_at"],
    postgresql_using="btree",
)
```

---

### Order of implementation (Part 2)

1. `core/memory.py` — new file, `get_conversation_history()`
2. `core/ai/intent_classifier.py` — add `history` parameter
3. `channels/widget.py` — load + pass history to all branches
4. `core/workflows/wismo.py` — use history in order selection
5. Index migration (if needed)
6. Verify: import + 287 tests

---

## Verification Checklist

After each step:

```bash
# 1. Imports resolve
python -c "from app.main import app"

# 2. Tests pass
cd api && python -m pytest tests/ -v --tb=short -q 2>&1 | tail -5

# 3. Policy Engine smoke test
python -c "
from app.core.policies.engine import PolicyEngine
p = PolicyEngine('test')
r = p.evaluate('wismo', {})
assert r['auto_notify'] == True
assert r['notification_channels'] == ['widget']
assert r['escalation_delay_days'] == 7
print('wismo policy OK')
"

# 4. Memory smoke test
python -c "
from app.core.memory import get_conversation_history
h = get_conversation_history('nonexistent', 'nonexistent')
assert h == []
print('memory OK')
"
```

## Rollback

| Step | Rollback |
|------|----------|
| models.py column | Drop column + migrate down |
| engine.py changes | Revert file |
| wismo.py changes | Revert file |
| memory.py | Delete file |
| intent_classifier.py changes | Revert signature |
| widget.py changes | Revert all branches |
