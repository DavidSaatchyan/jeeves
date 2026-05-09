from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def check_sla_breaches(db: Session) -> list[dict]:
    rows = db.execute(
        text("""
            SELECT id, workflow_id, tenant_id, reason, created_at
            FROM escalations
            WHERE status NOT IN ('RESOLVED', 'CLOSED')
              AND created_at < :threshold
        """),
        {"threshold": datetime.utcnow() - timedelta(hours=24)},
    ).fetchall()

    breaches = []
    for r in rows:
        breaches.append({
            "escalation_id": str(r[0]),
            "workflow_id": str(r[1]),
            "tenant_id": r[2],
            "reason": r[3],
            "created_at": r[4],
            "sla_breached_at": datetime.utcnow(),
        })
        logger.warning("SLA breach: escalation %s for workflow %s", r[0], r[1])

    return breaches


def requeue_sla_breached(db: Session, escalation_id: str) -> None:
    db.execute(
        text("UPDATE escalations SET sla_breached = TRUE, updated_at = :now WHERE id = :id"),
        {"now": datetime.utcnow(), "id": escalation_id},
    )
    db.commit()
