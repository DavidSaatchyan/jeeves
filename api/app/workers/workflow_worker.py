from __future__ import annotations

import logging

from ..core.workflows.scheduler import get_due_jobs

logger = logging.getLogger(__name__)


async def process_scheduled_jobs() -> None:
    jobs = await get_due_jobs()
    for job in jobs:
        logger.info("processing scheduled job: %s", job.get("job_id"))
