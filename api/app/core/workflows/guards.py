from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


async def check_workflow_lock(db: Session, workflow_id: UUID) -> bool:
    row = db.execute(
        text("SELECT locked_until FROM workflows WHERE id = :id"),
        {"id": workflow_id},
    ).first()
    if not row:
        return False
    if row[0] is None:
        return True
    from datetime import datetime
    return row[0] < datetime.utcnow()


async def check_no_active_workflow(db: Session, tenant_id: UUID, workflow_type: str, customer_id: str) -> bool:
    row = db.execute(
        text("""
            SELECT id FROM workflows
            WHERE tenant_id = :tid AND workflow_type = :wt AND customer_id = :cid
              AND status IN ('active', 'paused')
            LIMIT 1
        """),
        {"tid": tenant_id, "wt": workflow_type, "cid": customer_id},
    ).first()
    return row is None



