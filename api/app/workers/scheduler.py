from __future__ import annotations

import asyncio
import logging

from ..core.workflows.scheduler import get_due_jobs
from .base import Worker

logger = logging.getLogger(__name__)


class SchedulerWorker(Worker):
    name = "scheduler"
    poll_interval: int = 5

    async def run(self) -> None:
        while True:
            try:
                jobs = await get_due_jobs()
                for job in jobs:
                    logger.info("dispatching scheduled job: %s", job.get("job_id"))
            except Exception as e:
                logger.exception("scheduler poll error: %s", e)
            await asyncio.sleep(self.poll_interval)
