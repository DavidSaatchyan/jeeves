from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..events.schemas import CanonicalEvent

logger = logging.getLogger(__name__)


async def replay_workflow(db: Session, workflow_id: UUID) -> list[dict[str, Any]]:
    transitions = db.execute(
        text("""
            SELECT from_state, to_state, trigger_event, decision_reason, created_at
            FROM workflow_transitions
            WHERE workflow_id = :wid
            ORDER BY created_at ASC
        """),
        {"wid": workflow_id},
    ).fetchall()

    timeline = db.execute(
        text("""
            SELECT event_type, entity_type, entity_id, payload, created_at
            FROM timeline_events
            WHERE entity_type = 'workflow' AND entity_id = :wid
            ORDER BY created_at ASC
        """),
        {"wid": str(workflow_id)},
    ).fetchall()

    return {
        "workflow_id": str(workflow_id),
        "transitions": [
            {
                "from_state": t[0],
                "to_state": t[1],
                "trigger_event": t[2],
                "decision_reason": t[3],
                "timestamp": t[4].isoformat() if hasattr(t[4], "isoformat") else str(t[4]),
            }
            for t in transitions
        ],
        "timeline_events": [
            {
                "event_type": t[0],
                "entity_type": t[1],
                "entity_id": t[2],
                "payload": t[3],
                "timestamp": t[4].isoformat() if hasattr(t[4], "isoformat") else str(t[4]),
            }
            for t in timeline
        ],
    }


async def replay_and_revalidate(db: Session, workflow_id: UUID) -> dict[str, Any]:
    replay_data = await replay_workflow(db, workflow_id)

    from ..workflows.transitions import validate_transition

    for i in range(1, len(replay_data["transitions"])):
        prev = replay_data["transitions"][i - 1]
        curr = replay_data["transitions"][i]
        if prev["to_state"] != curr["from_state"]:
            logger.warning(
                "replay gap at step %d: expected from_state=%s, got %s",
                i, prev["to_state"], curr["from_state"],
            )

    return replay_data
