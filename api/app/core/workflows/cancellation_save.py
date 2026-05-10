from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from ..events.schemas import CanonicalEvent
from ..commerce.customer import CustomerService
from ..commerce.subscription import SubscriptionService
from ...integrations.recharge.actions import (
    execute_pause_subscription,
    execute_skip_shipment,
    execute_delay_renewal,
    execute_cancel_subscription,
    fetch_subscription_state,
)
from ...shared.locks import workflow_lock
from ..policies.approval_rules import get_allowed_save_actions
from ..policies.escalation_rules import should_escalate
from ..ai.classifier import classify_intent
from ..ai.sentiment import detect_frustration
from ..communications.service import send_communication
from ..escalations.manager import EscalationManager
from .runtime import Workflow
from .registry import register_workflow

logger = logging.getLogger(__name__)


class CancellationSaveWorkflow(Workflow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.intent_category: str = ""
        self.selected_action: str = ""
        self.allowed_actions: list[str] = []

    async def handle_event(self, event: CanonicalEvent, db: Session) -> None:
        async with workflow_lock(self.workflow_id) as acquired:
            if not acquired:
                logger.warning("could not acquire lock for workflow %s", self.workflow_id)
                return

            state_handlers = {
                "INTENT_DETECTED": self._handle_intent_detected,
                "VALIDATING": self._handle_validating,
                "CLASSIFYING_INTENT": self._handle_classifying_intent,
                "SELECTING_SAVE_FLOW": self._handle_selecting_save_flow,
                "SAVE_OFFER_PENDING": self._handle_save_offer_pending,
                "SAVE_OFFER_SENT": self._handle_save_offer_sent,
                "WAITING_CUSTOMER_DECISION": self._handle_waiting_decision,
                "EXECUTING_ACTION": self._handle_executing_action,
            }

            handler = state_handlers.get(self.current_state)
            if handler:
                await handler(event, db)
            else:
                logger.warning("no handler for state %s", self.current_state)

    async def _handle_intent_detected(self, event: CanonicalEvent, db: Session) -> None:
        await self.transition("VALIDATING", event, db, reason="cancellation_intent_detected")

    async def _handle_validating(self, event: CanonicalEvent, db: Session) -> None:
        subscription_id = event.payload.get("subscription_id", "")
        sub_service = SubscriptionService(db)
        sub = sub_service.get_by_external_id(subscription_id)

        if not sub:
            logger.warning("subscription %s not found, failing", subscription_id)
            await self.transition("FAILED", event, db, reason="subscription_not_found")
            return

        if sub["status"] != "active":
            logger.info("subscription %s not active (%s), no save flow needed", subscription_id, sub["status"])
            await self.transition("CANCELLED", event, db, reason="subscription_not_active")
            return

        await self.transition("CLASSIFYING_INTENT", event, db, reason="validation_passed")

    async def _handle_classifying_intent(self, event: CanonicalEvent, db: Session) -> None:
        customer_message = event.payload.get("message", "")
        classification = await classify_intent(customer_message)
        self.intent_category = classification.get("category", "hard_intent")

        _record_ai_interaction(
            db=db, tenant_id=event.tenant_id, workflow_id=self.workflow_id,
            input_data={"message": customer_message},
            output_data=classification,
            interaction_type="intent_classification",
        )

        if classification.get("confidence", 0) < 0.3:
            logger.warning("low confidence intent classification, escalating")
            await self.transition("ESCALATED", event, db, reason="low_confidence_intent")
            return

        if self.intent_category == "not_cancellation":
            await self.transition("CANCELLED", event, db, reason="not_cancellation_intent")
            return

        await self.transition("SELECTING_SAVE_FLOW", event, db, reason=f"intent_{self.intent_category}")

    async def _handle_selecting_save_flow(self, event: CanonicalEvent, db: Session) -> None:
        subscription_id = event.payload.get("subscription_id", "")
        sub_service = SubscriptionService(db)
        sub = sub_service.get_by_external_id(subscription_id)
        sub_status = sub["status"] if sub else ""

        self.allowed_actions = get_allowed_save_actions(sub_status, event.tenant_id)

        if not self.allowed_actions:
            logger.info("no save actions allowed for this subscription")
            await self.transition("CANCELLED", event, db, reason="no_save_actions_allowed")
            return

        if self.intent_category in ("hard_intent", "billing_problem"):
            await self._escalate(event, db, f"{self.intent_category}_needs_escalation")
            return
        elif self.intent_category == "soft_intent":
            self.selected_action = self.allowed_actions[0]
        else:
            self.selected_action = "pause"

        await self.transition("SAVE_OFFER_PENDING", event, db, reason=f"selected_{self.selected_action}")

    async def _handle_save_offer_pending(self, event: CanonicalEvent, db: Session) -> None:
        customer_id = event.payload.get("customer_id", "")
        customer = CustomerService(db).get_by_id(customer_id)

        comm_context = {
            "customer_name": customer.get("name", "") if customer else "",
            "email": customer.get("email", "") if customer else "",
            "offer_type": self.selected_action,
            "subscription_id": event.payload.get("subscription_id", ""),
        }

        comm_id = await send_communication(
            db=db,
            tenant_id=event.tenant_id,
            customer_id=customer_id,
            channel="email",
            template_name="save_offer",
            context=comm_context,
            workflow_id=str(self.workflow_id),
        )

        if comm_id:
            await self.transition("SAVE_OFFER_SENT", event, db, reason=f"save_offer_{self.selected_action}_sent")
        else:
            await self.transition("ESCALATED", event, db, reason="save_offer_comms_failed")

    async def _handle_save_offer_sent(self, event: CanonicalEvent, db: Session) -> None:
        await self.transition("WAITING_CUSTOMER_DECISION", event, db, reason="offer_sent_waiting_decision")

    async def _handle_waiting_decision(self, event: CanonicalEvent, db: Session) -> None:
        if event.event_type == "customer_message_cancellation":
            msg = event.payload.get("message", "")
            sentiment = await detect_frustration(msg)
            if sentiment.get("level") in ("medium", "high"):
                should_esc, esc_reason = should_escalate(sentiment["level"], 0, event.tenant_id)
                if should_esc:
                    await self._escalate(event, db, esc_reason)
                    return
            await self.transition("CANCELLED", event, db, reason="customer_confirmed_cancellation")

        elif event.event_type == "customer_payment_method_updated":
            await self.transition("EXECUTING_ACTION", event, db, reason="payment_updated_proceed")

        elif event.event_type == "customer_frustrated":
            msg = event.payload.get("message", "")
            sentiment = await detect_frustration(msg)
            if sentiment.get("level") in ("medium", "high"):
                await self._escalate(event, db, f"frustration_{sentiment['level']}")

        elif event.event_type == "workflow_timeout":
            await self.transition("EXPIRED", event, db, reason="customer_decision_timeout")

    async def _handle_executing_action(self, event: CanonicalEvent, db: Session) -> None:
        subscription_id = event.payload.get("subscription_id", "")

        result = None
        if self.selected_action == "pause":
            result = await execute_pause_subscription(event.tenant_id, subscription_id, db, "customer_request")
        elif self.selected_action == "skip":
            result = await execute_skip_shipment(event.tenant_id, subscription_id, db)
        elif self.selected_action == "delay":
            result = await execute_delay_renewal(event.tenant_id, subscription_id, db, 7)

        if result:
            await self.transition("RETAINED", event, db, reason=f"save_action_{self.selected_action}_executed")
        else:
            await self.transition("FAILED", event, db, reason=f"save_action_{self.selected_action}_failed")

    async def _escalate(self, event: CanonicalEvent, db: Session, reason: str) -> None:
        mgr = EscalationManager(db)
        mgr.create(
            tenant_id=event.tenant_id,
            workflow_id=self.workflow_id,
            reason=reason,
            source="cancellation_save",
            metadata={"current_state": self.current_state, "intent": self.intent_category},
        )
        mgr.pause_workflow(self.workflow_id)
        await self.transition("ESCALATED", event, db, reason=reason)


def _record_ai_interaction(db: Session, tenant_id: str, workflow_id: UUID,
                            input_data: dict, output_data: dict,
                            interaction_type: str) -> str:
    from uuid import uuid4
    from datetime import datetime
    from sqlalchemy import text

    iid = uuid4()
    db.execute(
        text("""
            INSERT INTO ai_interactions (id, tenant_id, workflow_id, interaction_type, input_data, output_data, created_at)
            VALUES (:id, :tid, :wid, :itype, :input, :output, :now)
        """),
        {
            "id": iid, "tid": tenant_id, "wid": workflow_id,
            "itype": interaction_type, "input": input_data,
            "output": output_data, "now": datetime.utcnow(),
        },
    )
    return str(iid)


register_workflow("cancellation_save", CancellationSaveWorkflow)
