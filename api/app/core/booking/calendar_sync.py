"""Calendar sync — Phase 5 stub. Full implementation in Phase 6+.

Interface documented for future Google/Outlook/etc integration.
"""

from __future__ import annotations

import logging
from uuid import UUID

from ...models import Appointment

logger = logging.getLogger(__name__)


async def push_to_calendar(appointment: Appointment, provider: str = "google") -> str | None:
    """Push appointment to external calendar. Returns external event ID or None."""
    logger.info(
        "calendar sync stub: push appointment %s to %s (would create event)",
        appointment.id, provider,
    )
    return None


async def pull_from_calendar(provider: str, calendar_id: str) -> list[dict]:
    """Pull events from external calendar. Returns list of event dicts."""
    logger.info("calendar sync stub: pull from %s calendar %s", provider, calendar_id)
    return []


async def sync_calendar(tenant_id: UUID, provider: str) -> dict:
    """Bi-directional sync stub. Returns stats dict."""
    logger.info("calendar sync stub: sync tenant %s %s (0 events processed)", tenant_id, provider)
    return {"synced": 0, "created": 0, "updated": 0, "deleted": 0}
