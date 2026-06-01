from __future__ import annotations

import logging
from datetime import datetime, date, time, timedelta
from uuid import uuid4

from .base import (
    AbstractCalendarProvider,
    CalendarProviderError,
    CalendarSlot,
    CalendarEvent,
)

logger = logging.getLogger(__name__)


class GoogleCalendarProvider(AbstractCalendarProvider):
    """Google Calendar integration via OAuth 2.0.

    Requires Google API credentials (client_id, client_secret, refresh_token).
    The token is stored in the CalendarConnection model and refreshed automatically.
    """

    def __init__(
        self,
        access_token: str,
        refresh_token: str | None = None,
        token_expiry: datetime | None = None,
    ) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.token_expiry = token_expiry
        self._service = None

    def _get_service(self):
        """Lazy-init the Google Calendar service with current tokens."""
        if self._service is not None:
            return self._service
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError:
            raise CalendarProviderError(
                "google-api-python-client is not installed. "
                "Run: pip install google-api-python-client google-auth-oauthlib"
            )

        creds = Credentials(
            token=self.access_token,
            refresh_token=self.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self._get_client_id(),
            client_secret=self._get_client_secret(),
        )
        self._service = build("calendar", "v3", credentials=creds)
        return self._service

    def _get_client_id(self) -> str:
        from ...config import get_settings
        return get_settings().google_client_id

    def _get_client_secret(self) -> str:
        from ...config import get_settings
        return get_settings().google_client_secret

    def _map_event(self, raw: dict) -> CalendarEvent:
        return CalendarEvent(
            external_id=raw.get("id", ""),
            summary=raw.get("summary", ""),
            start=self._parse_dt(raw.get("start", {})),
            end=self._parse_dt(raw.get("end", {})),
            status="confirmed" if raw.get("status") == "confirmed" else "cancelled" if raw.get("status") == "cancelled" else "scheduled",
            provider_name="",
            patient_id=(raw.get("extendedProperties") or {}).get("private", {}).get("patientId"),
            notes=raw.get("description"),
            extended_properties=raw.get("extendedProperties"),
        )

    def _parse_dt(self, dt_obj: dict) -> datetime:
        if "dateTime" in dt_obj:
            return datetime.fromisoformat(dt_obj["dateTime"])
        if "date" in dt_obj:
            return datetime.fromisoformat(dt_obj["date"])
        return datetime.utcnow()

    def _format_dt(self, dt: datetime) -> dict:
        return {"dateTime": dt.isoformat(), "timeZone": "UTC"}

    def _status_to_google(self, status: str | None) -> str | None:
        if status in ("cancelled", "no_show"):
            return "cancelled"
        return "confirmed"

    async def list_calendars(self) -> list[dict]:
        try:
            service = self._get_service()
            result = service.calendarList().list().execute()
            items = result.get("items", [])
            return [
                {"id": c["id"], "summary": c.get("summary", ""), "description": c.get("description")}
                for c in items
            ]
        except Exception as e:
            raise CalendarProviderError(f"Failed to list calendars: {e}") from e

    async def list_events(
        self,
        calendar_id: str,
        time_min: datetime | None = None,
        time_max: datetime | None = None,
        status_filter: str | None = None,
    ) -> list[CalendarEvent]:
        try:
            service = self._get_service()
            params: dict = {
                "calendarId": calendar_id,
                "singleEvents": True,
                "orderBy": "startTime",
            }
            if time_min:
                params["timeMin"] = time_min.isoformat()
            if time_max:
                params["timeMax"] = time_max.isoformat()

            result = service.events().list(**params).execute()
            items = result.get("items", [])

            events = [self._map_event(e) for e in items]

            if status_filter:
                events = [e for e in events if e.status == status_filter]

            return events
        except Exception as e:
            raise CalendarProviderError(f"Failed to list events: {e}") from e

    async def get_event(self, calendar_id: str, event_id: str) -> CalendarEvent | None:
        try:
            service = self._get_service()
            result = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
            return self._map_event(result)
        except Exception as e:
            if "not found" in str(e).lower():
                return None
            raise CalendarProviderError(f"Failed to get event {event_id}: {e}") from e

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
        try:
            service = self._get_service()
            body: dict = {
                "summary": summary,
                "start": self._format_dt(start),
                "end": self._format_dt(end),
                "status": "confirmed",
            }
            extended: dict = {"private": {}}
            if patient_id:
                extended["private"]["patientId"] = patient_id
            if provider_name:
                extended["private"]["providerName"] = provider_name
            if extended["private"]:
                body["extendedProperties"] = extended
            if notes:
                body["description"] = notes

            result = service.events().insert(calendarId=calendar_id, body=body).execute()
            return self._map_event(result)
        except Exception as e:
            raise CalendarProviderError(f"Failed to create event: {e}") from e

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
        try:
            service = self._get_service()
            body: dict = {}
            if summary is not None:
                body["summary"] = summary
            if start is not None:
                body["start"] = self._format_dt(start)
            if end is not None:
                body["end"] = self._format_dt(end)
            if status is not None:
                body["status"] = self._status_to_google(status)
            if notes is not None:
                body["description"] = notes

            result = service.events().patch(calendarId=calendar_id, eventId=event_id, body=body).execute()
            return self._map_event(result)
        except Exception as e:
            raise CalendarProviderError(f"Failed to update event {event_id}: {e}") from e

    async def cancel_event(self, calendar_id: str, event_id: str) -> bool:
        try:
            service = self._get_service()
            service.events().cancel(calendarId=calendar_id, eventId=event_id).execute()
            return True
        except Exception as e:
            if "not found" in str(e).lower():
                return False
            raise CalendarProviderError(f"Failed to cancel event {event_id}: {e}") from e

    async def get_available_slots(
        self,
        calendar_id: str,
        date_str: str,
        slot_duration_minutes: int = 30,
        buffer_minutes: int = 5,
        working_hours_start: str = "09:00",
        working_hours_end: str = "17:00",
    ) -> list[CalendarSlot]:
        try:
            target_date = date.fromisoformat(date_str)
            day_start = datetime.combine(target_date, time.fromisoformat(working_hours_start))
            day_end = datetime.combine(target_date, time.fromisoformat(working_hours_end))

            events = await self.list_events(
                calendar_id=calendar_id,
                time_min=day_start,
                time_max=day_end,
            )
            booked: list[tuple[datetime, datetime]] = [
                (e.start, e.end) for e in events if e.status != "cancelled"
            ]

            slots: list[CalendarSlot] = []
            cursor = day_start
            while cursor + timedelta(minutes=slot_duration_minutes) <= day_end:
                slot_end = cursor + timedelta(minutes=slot_duration_minutes)
                if not self._overlaps(cursor, slot_end, booked):
                    slots.append(CalendarSlot(
                        start=cursor,
                        end=slot_end,
                        provider_name=calendar_id,
                        provider_specialty=None,
                        slot_token=str(uuid4()),
                        calendar_id=calendar_id,
                    ))
                cursor += timedelta(minutes=slot_duration_minutes + buffer_minutes)

            return slots
        except Exception as e:
            raise CalendarProviderError(f"Failed to get available slots: {e}") from e

    def _overlaps(self, start: datetime, end: datetime, booked: list[tuple[datetime, datetime]]) -> bool:
        for bs, be in booked:
            if start < be and end > bs:
                return True
        return False
