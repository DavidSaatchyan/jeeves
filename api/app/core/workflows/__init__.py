from __future__ import annotations

import logging

from .appointment import AppointmentWorkflow
from .registry import register_workflow

logger = logging.getLogger(__name__)


def init_workflows() -> None:
    register_workflow("appointment", AppointmentWorkflow)
    logger.info("workflow initialized: appointment")
