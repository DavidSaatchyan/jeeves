from __future__ import annotations

import logging

from .appointment import AppointmentWorkflow
from .followup import FollowupWorkflow
from .marketing import MarketingWorkflow
from .registry import register_workflow

logger = logging.getLogger(__name__)


def init_workflows() -> None:
    register_workflow("appointment", AppointmentWorkflow)
    register_workflow("marketing", MarketingWorkflow)
    register_workflow("followup", FollowupWorkflow)
    logger.info("workflows initialized: appointment, marketing, followup")
