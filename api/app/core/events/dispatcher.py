from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from .deduplicator import is_duplicate
from .schemas import CanonicalEvent

logger = logging.getLogger(__name__)


async def dispatch_event(event: CanonicalEvent, db: Session) -> str | None:
    if await is_duplicate(event.event_id):
        logger.info("duplicate event skipped: %s", event.event_id)
        return None

    from ..workflows.registry import route_event
    await route_event(event, db)
    return event.event_id
