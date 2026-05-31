from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ..communications.delivery import send_whatsapp_message
from ..events.schemas import CanonicalEvent
from .runtime import Workflow

logger = logging.getLogger(__name__)

FOLLOWUP_STATES: set[str] = {
    "VISIT_COMPLETED",
    "DAY_1_CHECK",
    "DAY_7_CHECK",
    "DAY_30_CHECK",
    "MEDICATION_ADHERENCE",
    "SATISFACTION_SURVEY",
    "CLOSED",
    "ESCALATED",
    "EXPIRED",
}

TRANSITION_TABLE: dict[str, list[str]] = {
    "VISIT_COMPLETED":          ["DAY_1_CHECK", "ESCALATED", "EXPIRED"],
    "DAY_1_CHECK":              ["DAY_7_CHECK", "ESCALATED", "EXPIRED"],
    "DAY_7_CHECK":              ["DAY_30_CHECK", "ESCALATED", "EXPIRED"],
    "DAY_30_CHECK":             ["MEDICATION_ADHERENCE", "ESCALATED", "EXPIRED"],
    "MEDICATION_ADHERENCE":     ["SATISFACTION_SURVEY", "ESCALATED", "EXPIRED"],
    "SATISFACTION_SURVEY":      ["CLOSED", "ESCALATED", "EXPIRED"],
    "CLOSED":                   ["EXPIRED"],
    "ESCALATED":                ["CLOSED", "EXPIRED"],
    "EXPIRED":                  [],
}


class FollowupWorkflow(Workflow):

    async def handle_event(self, event: CanonicalEvent, db: Session) -> None:
        if event.event_type == "visit_completed":
            await self._on_visit_completed(event, db)
        elif event.event_type == "followup_due":
            await self._on_followup_step(event, db)
        elif event.event_type == "patient_responded":
            await self._on_patient_response(event, db)
        else:
            logger.warning("followup workflow %s: unhandled event type %s", self.workflow_id, event.event_type)

    async def _on_visit_completed(self, event: CanonicalEvent, db: Session) -> None:
        payload = event.payload or {}
        phone = payload.get("phone_number_id")
        token = payload.get("access_token")
        wa_id = payload.get("wa_id")
        message = payload.get("message") or _default_day1_message(payload)

        if phone and token and wa_id:
            try:
                await send_whatsapp_message(phone, token, wa_id, message)
            except Exception:
                logger.exception("followup %s: failed to send day1 message", self.workflow_id)

        await self.transition("DAY_1_CHECK", event, db, reason="visit_completed_day1_sent")

    async def _on_followup_step(self, event: CanonicalEvent, db: Session) -> None:
        state = self.current_state
        payload = event.payload or {}
        phone = payload.get("phone_number_id")
        token = payload.get("access_token")
        wa_id = payload.get("wa_id")

        next_state = _next_step(state)
        if not next_state:
            return

        message = payload.get("message") or _step_message(state, payload)
        if phone and token and wa_id and message:
            try:
                await send_whatsapp_message(phone, token, wa_id, message)
            except Exception:
                logger.exception("followup %s: failed to send step message", self.workflow_id)

        await self.transition(next_state, event, db, reason=f"followup_step_{state}_to_{next_state}")

    async def _on_patient_response(self, event: CanonicalEvent, db: Session) -> None:
        payload = event.payload or {}
        intent = payload.get("intent", "general")

        if intent in ("emergency", "followup_feeling_bad", "followup_medication_not"):
            await self.transition("ESCALATED", event, db, reason=f"patient_reported_issue_{intent}")
            phone = payload.get("phone_number_id")
            token = payload.get("access_token")
            wa_id = payload.get("wa_id")
            if phone and token and wa_id:
                try:
                    await send_whatsapp_message(phone, token, wa_id,
                        "We've notified our care team. Someone will reach out to you shortly. "
                        "If this is an emergency, please call 911 immediately.")
                except Exception:
                    logger.exception("followup %s: failed to send escalation message", self.workflow_id)

        elif intent in ("followup_feeling_good", "followup_medication_ok", "campaign_positive"):
            next_state = _next_step(self.current_state)
            if next_state:
                await self.transition(next_state, event, db, reason="patient_response_positive")


def _next_step(current: str) -> str | None:
    return {
        "DAY_1_CHECK": "DAY_7_CHECK",
        "DAY_7_CHECK": "DAY_30_CHECK",
        "DAY_30_CHECK": "MEDICATION_ADHERENCE",
        "MEDICATION_ADHERENCE": "SATISFACTION_SURVEY",
        "SATISFACTION_SURVEY": "CLOSED",
    }.get(current)


def _step_message(state: str, payload: dict) -> str | None:
    name = payload.get("patient_name", "there")
    clinic = payload.get("clinic_name", "your clinic")
    messages = {
        "DAY_1_CHECK": (
            f"Hi {name}! Just checking in after your recent visit to {clinic}. "
            f"How are you feeling today?"
        ),
        "DAY_7_CHECK": (
            f"Hi {name}! It's been a week since your visit. "
            f"We hope you're doing well. Any concerns or questions?"
        ),
        "DAY_30_CHECK": (
            f"Hi {name}! It's been a month since your visit to {clinic}. "
            f"How are you feeling? Are you satisfied with your progress?"
        ),
        "MEDICATION_ADHERENCE": (
            f"Hi {name}! Just a friendly reminder to take your medications as prescribed. "
            f"Are you having any trouble with your treatment plan?"
        ),
        "SATISFACTION_SURVEY": (
            f"Hi {name}! We'd love your feedback about your experience at {clinic}. "
            f"On a scale of 1-10, how likely are you to recommend us to a friend or family member?"
        ),
    }
    return messages.get(state)


def _default_day1_message(payload: dict) -> str:
    name = payload.get("patient_name", "there")
    clinic = payload.get("clinic_name", "your clinic")
    return (
        f"Hi {name}! Thank you for visiting {clinic}. "
        f"We hope everything went well. "
        f"How are you feeling? Reply STOP to opt out."
    )
