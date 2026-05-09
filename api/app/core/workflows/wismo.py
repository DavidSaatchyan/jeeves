from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from ..events.schemas import CanonicalEvent
from ..commerce.shipment import ShipmentService
from ...integrations.shopify.actions import fetch_order, fetch_fulfillments
from ...integrations.tracking.normalizer import normalize_tracking_event
from ...shared.locks import workflow_lock
from ..ai.classifier import classify_wismo_risk
from ..ai.sentiment import detect_frustration
from ..ai.generator import generate_widget_message
from ..communications.service import send_communication
from ..escalations.manager import EscalationManager
from .runtime import Workflow
from .registry import register_workflow

logger = logging.getLogger(__name__)


class WismoWorkflow(Workflow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.shipment_data: dict[str, Any] = {}
        self.risk_category: str = ""

    async def handle_event(self, event: CanonicalEvent, db: Session) -> None:
        async with workflow_lock(self.workflow_id) as acquired:
            if not acquired:
                logger.warning("could not acquire lock for workflow %s", self.workflow_id)
                return

            state_handlers = {
                "INQUIRY_DETECTED": self._handle_inquiry_detected,
                "VALIDATING_IDENTITY": self._handle_validating_identity,
                "RETRIEVING_SHIPMENT": self._handle_retrieving_shipment,
                "NORMALIZING_SHIPMENT_STATE": self._handle_normalizing_state,
                "CLASSIFYING_RISK": self._handle_classifying_risk,
                "RESPONSE_PENDING": self._handle_response_pending,
                "RESPONSE_SENT": self._handle_response_sent,
                "WAITING_CUSTOMER": self._handle_waiting_customer,
            }

            handler = state_handlers.get(self.current_state)
            if handler:
                await handler(event, db)
            else:
                logger.warning("no handler for state %s", self.current_state)

    async def _handle_inquiry_detected(self, event: CanonicalEvent, db: Session) -> None:
        await self.transition("VALIDATING_IDENTITY", event, db, reason="wismo_inquiry_detected")

    async def _handle_validating_identity(self, event: CanonicalEvent, db: Session) -> None:
        order_id = event.payload.get("order_id", event.entity_id)
        customer_id = event.payload.get("customer_id", "")

        if not order_id:
            await self.transition("FAILED", event, db, reason="no_order_id")
            return

        order = await fetch_order(order_id)
        if not order:
            logger.warning("order %s not found in Shopify", order_id)
            await self.transition("FAILED", event, db, reason="order_not_found")
            return

        await self.transition("RETRIEVING_SHIPMENT", event, db, reason="identity_validated")

    async def _handle_retrieving_shipment(self, event: CanonicalEvent, db: Session) -> None:
        order_id = event.payload.get("order_id", event.entity_id)

        fulfillments = await fetch_fulfillments(order_id)
        if not fulfillments:
            logger.info("no fulfillments for order %s", order_id)
            self.shipment_data = {"status": "processing", "tracking": None}
        else:
            f = fulfillments[0]
            tracking = _extract_tracking(f)
            self.shipment_data = {
                "status": f.get("status", "unknown"),
                "tracking": tracking,
                "carrier": f.get("tracking_company", ""),
                "estimated_delivery": None,
            }

        await self.transition("NORMALIZING_SHIPMENT_STATE", event, db, reason="shipment_retrieved")

    async def _handle_normalizing_state(self, event: CanonicalEvent, db: Session) -> None:
        if self.shipment_data.get("tracking"):
            normalized = normalize_tracking_event({
                "tracking_number": self.shipment_data["tracking"],
                "carrier": self.shipment_data.get("carrier", ""),
                "status": self.shipment_data.get("status", ""),
            })
            self.shipment_data["canonical_state"] = normalized["canonical_state"]

        await self.transition("CLASSIFYING_RISK", event, db, reason="state_normalized")

    async def _handle_classifying_risk(self, event: CanonicalEvent, db: Session) -> None:
        customer_message = event.payload.get("message", "")
        shipment_status = self.shipment_data.get("canonical_state", self.shipment_data.get("status", ""))

        classification = await classify_wismo_risk(customer_message, shipment_status)
        self.risk_category = classification.get("category", "simple_wismo")

        _record_ai_interaction(
            db=db, tenant_id=event.tenant_id, workflow_id=self.workflow_id,
            input_data={"message": customer_message, "shipment_status": shipment_status},
            output_data=classification,
            interaction_type="wismo_risk_classification",
        )

        await self.transition("RESPONSE_PENDING", event, db, reason=f"risk_{self.risk_category}")

    async def _handle_response_pending(self, event: CanonicalEvent, db: Session) -> None:
        customer_id = event.payload.get("customer_id", "")
        order_id = event.payload.get("order_id", event.entity_id)
        status = self.shipment_data.get("canonical_state", self.shipment_data.get("status", "processing"))

        context = {
            "order_id": order_id,
            "tracking": self.shipment_data.get("tracking"),
            "status": status,
            "carrier": self.shipment_data.get("carrier", ""),
            "estimated_delivery": self.shipment_data.get("estimated_delivery", ""),
        }

        if self.risk_category == "escalation_risk":
            ai_message = await generate_widget_message(context, "wismo_escalation")
        else:
            ai_message = await generate_widget_message(context, "wismo_update")

        comm_context = {
            **context,
            "message": ai_message or f"Your order {order_id} is currently {status}.",
        }

        await send_communication(
            db=db,
            tenant_id=event.tenant_id,
            customer_id=customer_id,
            channel="widget",
            template_name="wismo_response",
            context=comm_context,
            workflow_id=str(self.workflow_id),
        )

        await self.transition("RESPONSE_SENT", event, db, reason=f"response_generated_{self.risk_category}")

    async def _handle_response_sent(self, event: CanonicalEvent, db: Session) -> None:
        if self.risk_category == "escalation_risk":
            await self._escalate(event, db, "escalation_risk_detected")
        else:
            await self.transition("WAITING_CUSTOMER", event, db, reason="response_sent_waiting")

    async def _handle_waiting_customer(self, event: CanonicalEvent, db: Session) -> None:
        if event.event_type == "customer_frustrated":
            msg = event.payload.get("message", "")
            sentiment = await detect_frustration(msg)
            if sentiment.get("level") in ("medium", "high"):
                await self._escalate(event, db, f"frustration_{sentiment['level']}")
                return

        if event.event_type == "tracking_updated":
            await self.transition("RETRIEVING_SHIPMENT", event, db, reason="tracking_updated_recheck")
        elif event.event_type == "workflow_timeout":
            await self.transition("EXPIRED", event, db, reason="customer_wait_timeout")

    async def _escalate(self, event: CanonicalEvent, db: Session, reason: str) -> None:
        mgr = EscalationManager(db)
        mgr.create(
            tenant_id=event.tenant_id,
            workflow_id=self.workflow_id,
            reason=reason,
            source="wismo",
            metadata={"current_state": self.current_state, "risk": self.risk_category},
        )
        mgr.pause_workflow(self.workflow_id)
        await self.transition("ESCALATED", event, db, reason=reason)


def _extract_tracking(fulfillment: dict) -> str | None:
    for tn in fulfillment.get("tracking_numbers", []):
        return tn
    return fulfillment.get("tracking_number")


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


register_workflow("wismo", WismoWorkflow)
