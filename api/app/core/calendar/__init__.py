from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from .base import AbstractCalendarProvider, CalendarProviderError
from .google import GoogleCalendarProvider


def get_calendar_provider(tenant_id: UUID, db: Session) -> AbstractCalendarProvider | None:
    """Get the calendar provider for a tenant, or None if no calendar is connected."""
    from ...models import CalendarConnection

    conn = db.query(CalendarConnection).filter(
        CalendarConnection.tenant_id == tenant_id,
        CalendarConnection.status == "connected",
    ).first()

    if not conn:
        return None

    if conn.provider == "google":
        return GoogleCalendarProvider(
            access_token=conn.access_token,
            refresh_token=conn.refresh_token,
            token_expiry=conn.token_expiry,
        )

    return None


__all__ = [
    "AbstractCalendarProvider",
    "CalendarProviderError",
    "GoogleCalendarProvider",
    "get_calendar_provider",
]
