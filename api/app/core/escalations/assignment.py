from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session


def assign_next_available(db: Session, escalation_id: str) -> str | None:
    operators = db.execute(
        text("SELECT id FROM operators WHERE status = 'available' ORDER BY load ASC LIMIT 1"),
    ).first()

    if not operators:
        return None

    operator_id = str(operators[0])
    now = datetime.utcnow()
    db.execute(
        text("UPDATE escalations SET assigned_to = :op, status = 'ASSIGNED', updated_at = :now WHERE id = :eid"),
        {"op": operator_id, "now": now, "eid": escalation_id},
    )

    db.execute(
        text("UPDATE operators SET load = load + 1, updated_at = :now WHERE id = :id"),
        {"now": now, "id": operator_id},
    )
    db.commit()
    return operator_id


def release_operator(operator_id: str, db: Session) -> None:
    db.execute(
        text("UPDATE operators SET load = GREATEST(load - 1, 0), updated_at = :now WHERE id = :id"),
        {"now": datetime.utcnow(), "id": operator_id},
    )
    db.commit()
