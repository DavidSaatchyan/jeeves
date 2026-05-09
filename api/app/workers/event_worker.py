from __future__ import annotations

import logging

from ..core.events.schemas import CanonicalEvent
from ..core.events.dispatcher import dispatch_event
from ..db import SessionLocal

logger = logging.getLogger(__name__)


async def process_event(event: CanonicalEvent) -> None:
    db = SessionLocal()
    try:
        result = await dispatch_event(event, db)
        if result:
            logger.info("event processed: %s", result)
    except Exception as e:
        logger.exception("event processing failed: %s", e)
    finally:
        db.close()
