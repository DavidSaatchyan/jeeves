from __future__ import annotations

import logging

from ..core.communications.service import send_pending_communications
from ..db import SessionLocal
from .base import Worker

logger = logging.getLogger(__name__)


class CommsWorker(Worker):
    name = "comms"

    async def run(self) -> None:
        db = SessionLocal()
        try:
            sent = await send_pending_communications(db)
            if sent:
                logger.info("comms worker sent %d messages", sent)
        except Exception as e:
            logger.exception("comms worker error: %s", e)
        finally:
            db.close()
