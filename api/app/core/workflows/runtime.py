from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..events.schemas import CanonicalEvent

logger = logging.getLogger(__name__)


class Workflow(ABC):
    def __init__(
        self,
        workflow_id: UUID,
        tenant_id: UUID,
        customer_id: str,
        workflow_type: str,
        current_state: str,
        status: str = "active",
        started_at: datetime | None = None,
    ):
        self.workflow_id = workflow_id
        self.tenant_id = tenant_id
        self.customer_id = customer_id
        self.workflow_type = workflow_type
        self.current_state = current_state
        self.status = status
        self.started_at = started_at or datetime.utcnow()

    @abstractmethod
    async def handle_event(self, event: CanonicalEvent, db: Session) -> None:
        ...

    async def transition(self, to_state: str, event: CanonicalEvent, db: Session, reason: str = "") -> None:
        from .transitions import validate_transition
        from ..timeline.recorder import record_transition

        if not validate_transition(self.workflow_type, self.current_state, to_state):
            logger.warning(
                "invalid transition %s → %s for workflow %s",
                self.current_state, to_state, self.workflow_id,
            )
            return

        from_state = self.current_state
        self.current_state = to_state

        record_transition(
            db=db,
            workflow_id=self.workflow_id,
            workflow_type=self.workflow_type,
            from_state=from_state,
            to_state=to_state,
            trigger_event=event.event_type,
            decision_reason=reason,
            policy_snapshot={},
        )

        db.commit()

        if to_state in ("RECOVERED", "FAILED", "EXPIRED", "CANCELLED", "RESOLVED", "RETAINED", "LOST", "CONVERTED", "CLOSED"):
            self.status = "completed"
        elif to_state == "ESCALATED":
            self.status = "escalated"
        elif to_state in ("PAUSED_RECONCILIATION",):
            self.status = "paused"

    async def pause(self, db: Session, reason: str = "") -> None:
        self.status = "paused"
        db.execute(
            text("UPDATE workflows SET status = 'paused' WHERE id = :id AND status = 'active'"),
            {"id": self.workflow_id},
        )

    async def resume(self, db: Session) -> None:
        if self.status == "paused":
            self.status = "active"
            db.execute(
                text("UPDATE workflows SET status = 'active' WHERE id = :id AND status = 'paused'"),
                {"id": self.workflow_id},
            )

    async def expire(self, db: Session) -> None:
        from ..events.schemas import CanonicalEvent

        ev = CanonicalEvent(
            event_type="workflow_timeout",
            event_source="workflow_runtime",
            tenant_id=str(self.tenant_id),
            entity_type="workflow",
            entity_id=str(self.workflow_id),
            payload={"workflow_type": self.workflow_type, "state": self.current_state},
        )
        await self.transition("EXPIRED", ev, db, reason="workflow_expiration")

    async def escalate(self, db: Session, reason: str = "") -> None:
        from ..events.schemas import CanonicalEvent

        ev = CanonicalEvent(
            event_type="manual_escalation",
            event_source="workflow_runtime",
            tenant_id=str(self.tenant_id),
            entity_type="workflow",
            entity_id=str(self.workflow_id),
            payload={"reason": reason},
        )
        await self.transition("ESCALATED", ev, db, reason=reason)
