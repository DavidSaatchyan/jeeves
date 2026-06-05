from __future__ import annotations

import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from ..db import SessionLocal
from ..integrations.resolver import get_crm_adapter_for_tenant
from ..models import Tenant
from .crm_sync import poll_crm_changes

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def poll_all_tenants() -> None:
    db = SessionLocal()
    try:
        tenants = db.execute(select(Tenant).where(Tenant.is_active)).scalars().all()
        for tenant in tenants:
            if not tenant.crm_config:
                continue
            adapter = get_crm_adapter_for_tenant(tenant)
            if not adapter:
                continue
            try:
                result = poll_crm_changes(tenant.id)
                logger.info("CRM poll for tenant %s: services=%s practitioners=%s clinic=%s",
                            tenant.id,
                            result.get("services", {}).get("imported", 0),
                            result.get("practitioners", {}).get("imported", 0),
                            result.get("clinic", {}).get("imported", 0))
            except Exception as e:
                logger.error("CRM poll failed for tenant %s: %s", tenant.id, e)
    finally:
        db.close()


def setup_scheduler(interval_minutes: int = 60) -> BackgroundScheduler | None:
    global _scheduler
    if os.environ.get("WORKER_TYPE", "api") != "scheduler":
        logger.info("WORKER_TYPE=api — CRM scheduler not started")
        return None

    if _scheduler is not None:
        return _scheduler

    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(
        poll_all_tenants,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id="crm_poll",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("CRM polling scheduler started (interval=%d min)", interval_minutes)
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("CRM polling scheduler shut down")
