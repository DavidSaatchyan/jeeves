from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


class CalendarProviderError(Exception):
    """Raised when a calendar operation fails."""


@dataclass
class CalendarSlot:
    start: datetime
    end: datetime
    provider_name: str
    provider_specialty: str | None
    slot_token: str
    calendar_id: str | None = None  # Google Calendar event ID after booking


@dataclass
class CalendarEvent:
    external_id: str
    summary: str
    start: datetime
    end: datetime
    status: str
    provider_name: str
    patient_id: str | None = None
    notes: str | None = None
    extended_properties: dict | None = None


class AbstractCalendarProvider(ABC):
    """Interface for external calendar integrations (Google, Outlook, etc.)."""

    @abstractmethod
    async def list_calendars(self) -> list[dict]:
        """Return available calendars (id, summary, description)."""
        ...

    @abstractmethod
    async def list_events(
        self,
        calendar_id: str,
        time_min: datetime | None = None,
        time_max: datetime | None = None,
        status_filter: str | None = None,
    ) -> list[CalendarEvent]:
        """List events in a calendar within a time range."""
        ...

    @abstractmethod
    async def get_event(self, calendar_id: str, event_id: str) -> CalendarEvent | None:
        """Get a single event by ID."""
        ...

    @abstractmethod
    async def create_event(
        self,
        calendar_id: str,
        summary: str,
        start: datetime,
        end: datetime,
        patient_id: str | None = None,
        notes: str | None = None,
        provider_name: str | None = None,
    ) -> CalendarEvent:
        """Create an event in the calendar. Returns the created event."""
        ...

    @abstractmethod
    async def update_event(
        self,
        calendar_id: str,
        event_id: str,
        summary: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        status: str | None = None,
        notes: str | None = None,
    ) -> CalendarEvent:
        """Update an existing event."""
        ...

    @abstractmethod
    async def cancel_event(self, calendar_id: str, event_id: str) -> bool:
        """Cancel/delete an event. Returns True if successful."""
        ...

    @abstractmethod
    async def get_available_slots(
        self,
        calendar_id: str,
        date: str,
        slot_duration_minutes: int = 30,
        buffer_minutes: int = 5,
        working_hours_start: str = "09:00",
        working_hours_end: str = "17:00",
    ) -> list[CalendarSlot]:
        """Get available time slots for a given date by checking existing events."""
        ...
