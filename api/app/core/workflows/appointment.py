from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ..events.schemas import CanonicalEvent
from .runtime import Workflow

logger = logging.getLogger(__name__)

APPOINTMENT_STATES: set[str] = {
    "STARTED",
    "AWAITING_INTENT",
    "CLASSIFYING",
    "CHECKING_SCHEDULE",
    "OFFERING_SLOTS",
    "CONFIRMING",
    "BOOKED",
    "RESCHEDULING",
    "CANCELLING",
    "REMINDER_SENT",
    "ARRIVED",
    "NO_SHOW",
    "COMPLETED",
    "CANCELLED",
    "ESCALATED",
    "EXPIRED",
}

TRANSITION_TABLE: dict[str, list[str]] = {
    "STARTED":              ["CLASSIFYING", "AWAITING_INTENT"],
    "AWAITING_INTENT":      ["CLASSIFYING", "ESCALATED", "EXPIRED"],
    "CLASSIFYING":          ["CHECKING_SCHEDULE", "AWAITING_INTENT", "CANCELLING", "ESCALATED"],
    "CHECKING_SCHEDULE":    ["OFFERING_SLOTS", "AWAITING_INTENT", "CANCELLED", "ESCALATED"],
    "OFFERING_SLOTS":       ["CONFIRMING", "AWAITING_INTENT", "CANCELLED", "ESCALATED"],
    "CONFIRMING":           ["BOOKED", "OFFERING_SLOTS", "CANCELLED", "ESCALATED"],
    "RESCHEDULING":         ["CHECKING_SCHEDULE", "BOOKED", "CANCELLED", "ESCALATED"],
    "CANCELLING":           ["CANCELLED", "AWAITING_INTENT"],
    "BOOKED":               ["REMINDER_SENT", "RESCHEDULING", "CANCELLING", "NO_SHOW", "COMPLETED", "ESCALATED"],
    "REMINDER_SENT":        ["ARRIVED", "NO_SHOW", "RESCHEDULING", "CANCELLING"],
    "ARRIVED":              ["COMPLETED", "NO_SHOW"],
    "NO_SHOW":              ["BOOKED", "COMPLETED", "CANCELLED"],
    "COMPLETED":            ["EXPIRED"],
    "CANCELLED":            ["EXPIRED"],
    "ESCALATED":            ["AWAITING_INTENT", "CANCELLED", "COMPLETED", "EXPIRED"],
    "EXPIRED":              [],
}


class AppointmentWorkflow(Workflow):
    """Appointment booking state machine."""

    async def handle_event(self, event: CanonicalEvent, db: Session) -> None:
        if event.event_type == "patient_message_received":
            await self._on_patient_message(event, db)
        elif event.event_type == "appointment_requested":
            await self._on_appointment_request(event, db)
        elif event.event_type == "slot_selected":
            await self._on_slot_selected(event, db)
        elif event.event_type == "reminder_due":
            await self._on_reminder_due(event, db)
        elif event.event_type == "patient_arrived":
            await self._on_patient_arrived(event, db)
        elif event.event_type == "no_show_detected":
            await self._on_no_show(event, db)
        else:
            logger.warning("appointment workflow %s: unhandled event type %s", self.workflow_id, event.event_type)

    async def _on_patient_message(self, event: CanonicalEvent, db: Session) -> None:
        state = self.current_state

        if state == "STARTED":
            await self.transition("CLASSIFYING", event, db, reason="workflow_started")

        elif state == "AWAITING_INTENT":
            await self.transition("CLASSIFYING", event, db, reason="patient_message_received")

        elif state == "CLASSIFYING":
            from ..ai.triage import triage_intent
            payload = event.payload or {}
            result = await triage_intent(
                message=payload.get("message", ""),
                conversation_history=payload.get("history"),
            )
            intent = result.get("intent", "general_question")
            urgency = result.get("urgency", "routine")

            if urgency == "emergency":
                await self.transition("ESCALATED", event, db, reason="emergency_detected")
            elif intent in ("book_appointment", "check_availability"):
                await self.transition("CHECKING_SCHEDULE", event, db, reason=f"intent={intent}")
            elif intent == "cancel_appointment":
                await self.transition("CANCELLING", event, db, reason="patient_requested_cancel")
            elif intent == "reschedule":
                await self.transition("RESCHEDULING", event, db, reason="patient_requested_reschedule")
            else:
                await self.transition("AWAITING_INTENT", event, db, reason=f"unclear_intent={intent}")

        elif state == "CHECKING_SCHEDULE":
            from ..booking import get_available_slots
            payload = event.payload or {}
            tenant_id = event.tenant_id
            slots = get_available_slots(
                db, tenant_id,
                provider_name=payload.get("provider_name"),
                specialty=payload.get("specialty"),
            )
            if slots:
                await self.transition("OFFERING_SLOTS", event, db, reason=f"found_{len(slots)}_slots")
            else:
                await self.transition("AWAITING_INTENT", event, db, reason="no_slots_available")

        elif state == "OFFERING_SLOTS":
            await self.transition("CONFIRMING", event, db, reason="patient_selected_slot")

        elif state == "CONFIRMING":
            await self._confirm_booking(event, db)

        elif state == "BOOKED":
            payload = event.payload or {}
            msg = (payload.get("message") or "").lower()
            if any(w in msg for w in ("cancel", "cancel", "remove", "delete", "cancel")):
                await self.transition("CANCELLING", event, db, reason="patient_requested_cancel")
            elif any(w in msg for w in ("reschedule", "change", "move", "different", "another")):
                await self.transition("RESCHEDULING", event, db, reason="patient_requested_reschedule")

        elif state == "CANCELLING":
            await self._cancel_booking(event, db)

        elif state == "RESCHEDULING":
            await self.transition("CHECKING_SCHEDULE", event, db, reason="reschedule_started")

    async def _on_appointment_request(self, event: CanonicalEvent, db: Session) -> None:
        await self.transition("AWAITING_INTENT", event, db, reason="appointment_requested")

    async def _on_slot_selected(self, event: CanonicalEvent, db: Session) -> None:
        if self.current_state in ("OFFERING_SLOTS", "CONFIRMING"):
            await self._confirm_booking(event, db)

    async def _on_reminder_due(self, event: CanonicalEvent, db: Session) -> None:
        if self.current_state == "BOOKED":
            await self.transition("REMINDER_SENT", event, db, reason="reminder_due")

    async def transition(self, to_state: str, event: CanonicalEvent, db: Session, reason: str = "") -> None:
        await super().transition(to_state, event, db, reason)
        if to_state in ("COMPLETED",):
            await self._fire_visit_completed(event, db)

    async def _on_patient_arrived(self, event: CanonicalEvent, db: Session) -> None:
        if self.current_state in ("BOOKED", "REMINDER_SENT"):
            await self.transition("ARRIVED", event, db, reason="patient_arrived")

    async def _fire_visit_completed(self, event: CanonicalEvent, db: Session) -> None:
        from .registry import route_event

        visit_event = CanonicalEvent(
            tenant_id=str(self.tenant_id),
            event_type="visit_completed",
            event_source="followup",
            entity_type="patient",
            entity_id=self.customer_id,
            payload={
                "patient_id": self.customer_id,
                "workflow_id": str(self.workflow_id),
                "tenant_id": str(self.tenant_id),
                "phone_number_id": (event.payload or {}).get("phone_number_id"),
                "access_token": (event.payload or {}).get("access_token"),
                "wa_id": (event.payload or {}).get("wa_id", self.customer_id),
                "patient_name": (event.payload or {}).get("patient_name"),
            },
        )
        await route_event(visit_event, db)

    async def _on_no_show(self, event: CanonicalEvent, db: Session) -> None:
        if self.current_state in ("BOOKED", "REMINDER_SENT", "ARRIVED"):
            await self.transition("NO_SHOW", event, db, reason="no_show_detected")

    async def _confirm_booking(self, event: CanonicalEvent, db: Session) -> None:
        from ..booking import book_appointment
        from ..booking.scheduler import SlotAlreadyBookedError
        from ..calendar import CalendarProviderError

        payload = event.payload or {}

        try:
            appt = book_appointment(
                db=db,
                tenant_id=self.tenant_id,
                patient_id=payload.get("patient_id"),
                slot_token=payload.get("slot_token", ""),
                provider_name=payload.get("provider_name", ""),
                start_time=payload.get("start_time"),
                end_time=payload.get("end_time"),
                reason=payload.get("reason"),
                source=payload.get("source", "whatsapp"),
            )
            await self.transition("BOOKED", event, db, reason=f"booked_{appt.id}")
        except SlotAlreadyBookedError:
            await self.transition("OFFERING_SLOTS", event, db, reason="slot_already_booked")
        except CalendarProviderError as e:
            logger.error("booking failed: %s", e)
            await self.transition("ESCALATED", event, db, reason="no_calendar_configured")

    async def _cancel_booking(self, event: CanonicalEvent, db: Session) -> None:
        from ..booking import cancel_appointment

        payload = event.payload or {}
        appointment_id = payload.get("appointment_id")
        if appointment_id:
            cancel_appointment(db, appointment_id, reason=payload.get("reason"))
        await self.transition("CANCELLED", event, db, reason="cancelled")
