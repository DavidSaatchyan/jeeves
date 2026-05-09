from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def get_by_workflow(db: Session, workflow_id: UUID, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    rows = db.execute(
        text("""
            SELECT id, event_type, entity_type, entity_id, payload, created_at
            FROM timeline_events
            WHERE entity_type = 'workflow' AND entity_id = :wid
            ORDER BY created_at DESC
            LIMIT :lim OFFSET :off
        """),
        {"wid": str(workflow_id), "lim": limit, "off": offset},
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_by_customer(db: Session, tenant_id: str, customer_id: str, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    rows = db.execute(
        text("""
            SELECT id, event_type, entity_type, entity_id, payload, created_at
            FROM timeline_events
            WHERE tenant_id = :tid AND entity_type = 'customer' AND entity_id = :cid
            ORDER BY created_at DESC
            LIMIT :lim OFFSET :off
        """),
        {"tid": tenant_id, "cid": customer_id, "lim": limit, "off": offset},
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_by_entity(db: Session, entity_type: str, entity_id: str, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    rows = db.execute(
        text("""
            SELECT id, event_type, entity_type, entity_id, payload, created_at
            FROM timeline_events
            WHERE entity_type = :et AND entity_id = :eid
            ORDER BY created_at DESC
            LIMIT :lim OFFSET :off
        """),
        {"et": entity_type, "eid": entity_id, "lim": limit, "off": offset},
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_by_date_range(
    db: Session, tenant_id: str, start: datetime, end: datetime, limit: int = 100, offset: int = 0
) -> list[dict[str, Any]]:
    rows = db.execute(
        text("""
            SELECT id, event_type, entity_type, entity_id, payload, created_at
            FROM timeline_events
            WHERE tenant_id = :tid AND created_at BETWEEN :start AND :end
            ORDER BY created_at DESC
            LIMIT :lim OFFSET :off
        """),
        {"tid": tenant_id, "start": start, "end": end, "lim": limit, "off": offset},
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": str(row[0]),
        "event_type": row[1],
        "entity_type": row[2],
        "entity_id": row[3],
        "payload": row[4],
        "created_at": row[5].isoformat() if hasattr(row[5], "isoformat") else row[5],
    }
