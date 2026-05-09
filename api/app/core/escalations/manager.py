from __future__ import annotations

import logging
from datetime import datetime
from uuid import uuid4
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from ...core.timeline.recorder import record_timeline_event

logger = logging.getLogger(__name__)

ESCALATION_STATES = ["OPEN", "ASSIGNED", "IN_PROGRESS", "WAITING_EXTERNAL", "RESOLVED", "CLOSED"]
VALID_TRANSITIONS = {
    "OPEN": ["ASSIGNED", "CLOSED"],
    "ASSIGNED": ["IN_PROGRESS", "WAITING_EXTERNAL", "CLOSED"],
    "IN_PROGRESS": ["WAITING_EXTERNAL", "RESOLVED", "CLOSED"],
    "WAITING_EXTERNAL": ["IN_PROGRESS", "RESOLVED", "CLOSED"],
    "RESOLVED": ["CLOSED"],
    "CLOSED": [],
}


class EscalationManager:
    def __init__(self, db: Session):
        self.db = db

    def create(self, tenant_id: str, workflow_id: UUID, reason: str,
               source: str = "workflow", metadata: dict | None = None) -> dict:
        eid = uuid4()
        now = datetime.utcnow()
        self.db.execute(
            text("""
                INSERT INTO escalations (id, tenant_id, workflow_id, status, reason, source, metadata, created_at, updated_at)
                VALUES (:id, :tid, :wid, 'OPEN', :reason, :source, :meta, :now, :now)
            """),
            {"id": eid, "tid": tenant_id, "wid": workflow_id,
             "reason": reason, "source": source, "meta": metadata or {}, "now": now},
        )

        record_timeline_event(
            db=self.db,
            event_type="escalation_created",
            entity_type="workflow",
            entity_id=str(workflow_id),
            tenant_id=tenant_id,
            payload={"escalation_id": str(eid), "reason": reason},
        )

        return {"id": str(eid), "status": "OPEN", "reason": reason}

    def transition(self, escalation_id: str, to_state: str) -> bool:
        row = self.db.execute(
            text("SELECT id, status FROM escalations WHERE id = :id"),
            {"id": escalation_id},
        ).first()
        if not row:
            return False

        from_state = row[1]
        allowed = VALID_TRANSITIONS.get(from_state, [])
        if to_state not in allowed:
            logger.warning("invalid escalation transition %s -> %s", from_state, to_state)
            return False

        now = datetime.utcnow()
        self.db.execute(
            text("UPDATE escalations SET status = :status, updated_at = :now WHERE id = :id"),
            {"status": to_state, "now": now, "id": escalation_id},
        )
        self.db.commit()
        return True

    def resolve(self, escalation_id: str, resolution: str = "") -> bool:
        return self.transition(escalation_id, "RESOLVED")

    def close(self, escalation_id: str) -> bool:
        return self.transition(escalation_id, "CLOSED")

    def assign(self, escalation_id: str, operator_id: str) -> bool:
        if not self.transition(escalation_id, "ASSIGNED"):
            return False
        self.db.execute(
            text("UPDATE escalations SET assigned_to = :op WHERE id = :id"),
            {"op": operator_id, "id": escalation_id},
        )
        self.db.commit()
        return True

    def get_active_for_workflow(self, workflow_id: UUID) -> list[dict]:
        rows = self.db.execute(
            text("SELECT id, status, reason, created_at FROM escalations "
                 "WHERE workflow_id = :wid AND status NOT IN ('RESOLVED', 'CLOSED')"),
            {"wid": workflow_id},
        ).fetchall()
        return [
            {"id": str(r[0]), "status": r[1], "reason": r[2], "created_at": r[3]}
            for r in rows
        ]

    def pause_workflow(self, workflow_id: UUID) -> None:
        self.db.execute(
            text("UPDATE workflows SET status = 'paused' WHERE id = :id AND status = 'active'"),
            {"id": workflow_id},
        )

    def resume_workflow(self, workflow_id: UUID) -> None:
        self.db.execute(
            text("UPDATE workflows SET status = 'active' WHERE id = :id AND status = 'paused'"),
            {"id": workflow_id},
        )
        self.db.commit()
