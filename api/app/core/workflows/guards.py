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


async def check_subscription_active(db: Session, subscription_id: str) -> bool:
    row = db.execute(
        text("SELECT status FROM subscriptions WHERE external_subscription_id = :sid"),
        {"sid": subscription_id},
    ).first()
    if not row:
        return True
    return row[0] == "active"


async def check_invoice_unpaid(db: Session, invoice_id: str) -> bool:
    row = db.execute(
        text("SELECT status FROM invoices WHERE external_invoice_id = :iid"),
        {"iid": invoice_id},
    ).first()
    if not row:
        return True
    return row[0] in ("open", "unpaid")
