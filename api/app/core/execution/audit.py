from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session


def record_action_audit(db: Session, tenant_id: str, workflow_id: str, action: str,
                         status: str, request: dict | None = None,
                         response: dict | None = None, error: str | None = None,
                         latency_ms: int | None = None) -> str:
    aid = uuid4()
    db.execute(
        text("""
            INSERT INTO agent_tool_logs (id, tenant_id, tool_name, status, request, response, error, latency_ms, created_at)
            VALUES (:id, :tid, :tool, :status, :req, :res, :err, :lat, :now)
        """),
        {
            "id": aid, "tid": tenant_id, "tool": action,
            "status": status, "req": request or {},
            "res": response, "err": error, "lat": latency_ms,
            "now": datetime.utcnow(),
        },
    )
    db.commit()
    return str(aid)
