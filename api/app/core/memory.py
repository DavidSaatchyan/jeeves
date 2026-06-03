from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import ChatLog

_MAX_MESSAGES = 15
_MAX_AGE_HOURS = 24


def get_conversation_history(
    tenant_id: str | UUID,
    customer_id: str,
    limit: int = _MAX_MESSAGES,
    max_age_hours: int = _MAX_AGE_HOURS,
    db: Session | None = None,
) -> list[dict]:
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        if isinstance(tenant_id, str):
            tenant_id = UUID(tenant_id)
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        rows = (
            db.execute(select(ChatLog).where(
                ChatLog.tenant_id == tenant_id,
                ChatLog.user_id == customer_id,
                ChatLog.created_at >= cutoff,
            )).scalars()
            .order_by(desc(ChatLog.created_at))
            .limit(limit)
            .all()
        )
    finally:
        if close_db:
            db.close()

    history = []
    for row in reversed(rows):
        if row.direction == "incoming" and row.message:
            history.append({"role": "customer", "content": row.message})
        elif row.direction == "outgoing" and row.response:
            history.append({"role": "assistant", "content": row.response})

    return history
