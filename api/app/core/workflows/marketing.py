from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from ..communications.delivery import send_whatsapp_message
from ..compliance.consent import ConsentManager
from ..events.schemas import CanonicalEvent
from .runtime import Workflow

logger = logging.getLogger(__name__)

MARKETING_STATES: set[str] = {
    "LEAD_CAPTURED",
    "QUALIFYING",
    "NURTURING",
    "APPOINTMENT_BOOKED",
    "FOLLOW_UP",
    "CONVERTED",
    "LOST",
    "ESCALATED",
    "EXPIRED",
}

TRANSITION_TABLE: dict[str, list[str]] = {
    "LEAD_CAPTURED":        ["QUALIFYING", "ESCALATED", "EXPIRED"],
    "QUALIFYING":           ["NURTURING", "LEAD_CAPTURED", "LOST", "ESCALATED", "EXPIRED"],
    "NURTURING":            ["APPOINTMENT_BOOKED", "LEAD_CAPTURED", "LOST", "ESCALATED", "EXPIRED"],
    "APPOINTMENT_BOOKED":   ["FOLLOW_UP", "LOST", "ESCALATED", "EXPIRED"],
    "FOLLOW_UP":            ["CONVERTED", "LOST", "ESCALATED", "EXPIRED"],
    "CONVERTED":            ["EXPIRED"],
    "LOST":                 ["LEAD_CAPTURED", "EXPIRED"],
    "ESCALATED":            ["LEAD_CAPTURED", "CONVERTED", "LOST", "EXPIRED"],
    "EXPIRED":              [],
}


class MarketingWorkflow(Workflow):

    async def handle_event(self, event: CanonicalEvent, db: Session) -> None:
        if event.event_type == "campaign_scheduled":
            await self._on_campaign_scheduled(event, db)
        elif event.event_type == "patient_responded":
            await self._on_patient_response(event, db)
        elif event.event_type == "nurture_due":
            await self._on_nurture_step(event, db)
        elif event.event_type == "appointment_requested":
            await self._on_appointment_booked(event, db)
        else:
            logger.warning("marketing workflow %s: unhandled event type %s", self.workflow_id, event.event_type)

    async def _on_campaign_scheduled(self, event: CanonicalEvent, db: Session) -> None:
        if not self._check_consent(db):
            await self.transition("LOST", event, db, reason="no_marketing_consent")
            return

        payload = event.payload or {}
        phone = payload.get("phone_number_id")
        token = payload.get("access_token")
        wa_id = payload.get("wa_id")
        message = payload.get("message") or _default_campaign_first_message(payload)

        if not phone or not token or not wa_id:
            logger.warning("marketing %s: missing whatsapp credentials in payload", self.workflow_id)
            return

        try:
            await send_whatsapp_message(phone, token, wa_id, message)
        except Exception:
            logger.exception("marketing %s: failed to send campaign message", self.workflow_id)

        await self.transition("QUALIFYING", event, db, reason="initial_campaign_message_sent")

    async def _on_patient_response(self, event: CanonicalEvent, db: Session) -> None:
        state = self.current_state
        payload = event.payload or {}
        intent = payload.get("intent", "general")

        if state == "QUALIFYING":
            if intent in ("campaign_positive", "appointment", "campaign_question"):
                if not self._check_consent(db):
                    await self.transition("LOST", event, db, reason="no_marketing_consent")
                    return
                await self._send_nurture_message(event, db)
                await self.transition("NURTURING", event, db, reason="patient_interested")
            elif intent in ("campaign_negative", "cancel", "general"):
                await self.transition("LOST", event, db, reason="patient_not_interested")
            else:
                await self.transition("LOST", event, db, reason=f"unclear_response_{intent}")

        elif state == "NURTURING":
            if intent == "appointment":
                await self._route_to_appointment(event, db)
                await self.transition("APPOINTMENT_BOOKED", event, db, reason="patient_booked_appointment")
            elif intent in ("campaign_negative", "cancel"):
                await self.transition("LOST", event, db, reason="patient_opted_out")
            else:
                await self.transition("NURTURING", event, db, reason="continue_nurturing")

        elif state == "APPOINTMENT_BOOKED":
            if intent in ("campaign_positive", "follow_up"):
                if not self._check_consent(db):
                    await self.transition("LOST", event, db, reason="no_marketing_consent")
                    return
                await self._send_followup_message(event, db)
                await self.transition("FOLLOW_UP", event, db, reason="follow_up_started")
            else:
                await self.transition("LOST", event, db, reason="no_follow_up_response")

        elif state == "FOLLOW_UP":
            await self.transition("CONVERTED", event, db, reason="patient_converted")

    async def _on_nurture_step(self, event: CanonicalEvent, db: Session) -> None:
        if self.current_state not in ("NURTURING",):
            return
        if not self._check_consent(db):
            await self.transition("LOST", event, db, reason="no_marketing_consent")
            return
        await self._send_nurture_message(event, db)

    async def _on_appointment_booked(self, event: CanonicalEvent, db: Session) -> None:
        if self.current_state in ("NURTURING",):
            await self.transition("APPOINTMENT_BOOKED", event, db, reason="appointment_booked_via_event")

    async def _send_nurture_message(self, event: CanonicalEvent, db: Session) -> None:
        payload = event.payload or {}
        phone = payload.get("phone_number_id")
        token = payload.get("access_token")
        wa_id = payload.get("wa_id")
        message = payload.get("message") or _default_nurture_message(payload)
        if phone and token and wa_id:
            try:
                await send_whatsapp_message(phone, token, wa_id, message)
            except Exception:
                logger.exception("marketing %s: failed to send nurture message", self.workflow_id)

    async def _send_followup_message(self, event: CanonicalEvent, db: Session) -> None:
        payload = event.payload or {}
        phone = payload.get("phone_number_id")
        token = payload.get("access_token")
        wa_id = payload.get("wa_id")
        message = payload.get("message") or _default_followup_message(payload)
        if phone and token and wa_id:
            try:
                await send_whatsapp_message(phone, token, wa_id, message)
            except Exception:
                logger.exception("marketing %s: failed to send follow-up message", self.workflow_id)

    def _check_consent(self, db: Session) -> bool:
        patient_id = UUID(self.customer_id) if isinstance(self.customer_id, str) else self.customer_id
        if not ConsentManager.is_valid(db, patient_id, "marketing", self.tenant_id):
            logger.info("marketing %s: no marketing consent for patient %s", self.workflow_id, self.customer_id)
            return False
        return True

    async def _route_to_appointment(self, event: CanonicalEvent, db: Session) -> None:
        from .registry import route_event

        appt_event = CanonicalEvent(
            tenant_id=str(self.tenant_id),
            event_type="patient_message_received",
            event_source="appointment",
            entity_type="patient",
            entity_id=self.customer_id,
            payload={
                "patient_id": self.customer_id,
                "message": event.payload.get("message", ""),
                "channel": "whatsapp",
                "source": "marketing_campaign",
            },
        )
        await route_event(appt_event, db)


def _default_campaign_first_message(payload: dict) -> str:
    name = payload.get("patient_name", "there")
    clinic = payload.get("clinic_name", "our clinic")
    return (
        f"Hi {name}! This is {clinic}. "
        f"We'd like to let you know about our latest health services available to you. "
        f"Would you like to learn more? Reply STOP to opt out."
    )


def _default_nurture_message(payload: dict) -> str:
    name = payload.get("patient_name", "there")
    return (
        f"Hi {name}! Just following up on our previous message. "
        f"We have some great options that might interest you. "
        f"Would you like to schedule a visit? Reply STOP to opt out."
    )


def _default_followup_message(payload: dict) -> str:
    name = payload.get("patient_name", "there")
    return (
        f"Hi {name}! We hope you had a great visit. "
        f"We'd love to hear your feedback. "
        f"Reply STOP to opt out."
    )
