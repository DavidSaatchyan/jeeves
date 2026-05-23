from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from ..events.schemas import CanonicalEvent
from ..policies.engine import PolicyEngine
from .runtime import Workflow

logger = logging.getLogger(__name__)

WISMO_INITIAL_STATE = "INQUIRY_DETECTED"
WISMO_TERMINAL_STATES = {"RESOLVED", "LOST", "ESCALATED"}


class WismoWorkflow(Workflow):
    async def handle_event(self, event: CanonicalEvent, db: Session) -> None:
        if not hasattr(self, "_policy_loaded"):
            self.wismo_policy = PolicyEngine(tenant_id=str(self.tenant_id), db=db).evaluate("wismo", {})
            self._policy_loaded = True

        if event.event_type in ("fulfillment_created", "tracking_updated", "order_created"):
            await self._handle_shopify_event(event, db)
        elif event.event_type == "intent:wismo":
            await self._handle_chat_inquiry(event, db)
        else:
            logger.warning("WISMO unknown event type: %s", event.event_type)

    async def _handle_shopify_event(self, event: CanonicalEvent, db: Session) -> None:
        if self.current_state == WISMO_INITIAL_STATE:
            await self.transition("VALIDATING_IDENTITY", event, db, reason="shopify_webhook_received")
        await self._validate_and_fetch(event, db)

    async def _handle_chat_inquiry(self, event: CanonicalEvent, db: Session) -> None:
        if self.current_state == WISMO_INITIAL_STATE:
            await self.transition("VALIDATING_IDENTITY", event, db, reason="chat_inquiry")

        if self.current_state == "WAITING_ORDER_SELECTION":
            await self._handle_order_selection(event, db)
            return

        await self._validate_and_fetch(event, db)

    async def _validate_and_fetch(self, event: CanonicalEvent, db: Session) -> None:
        if self.current_state not in ("VALIDATING_IDENTITY", "INQUIRY_DETECTED"):
            await self._resolve_if_terminal(db)
            return

        tenant_id = UUID(event.tenant_id)
        payload = event.payload or {}
        customer_id = payload.get("customer_id", self.customer_id)

        from .wismo_service import (
            fetch_order,
            fetch_fulfillments,
            find_orders_by_customer,
            parse_order_number,
            update_workflow_order,
        )

        order_id = payload.get("order_id", "")

        if not order_id:
            message = payload.get("message", "")
            parsed = parse_order_number(message) if message else None
            if parsed:
                order_id = parsed

        if order_id:
            order = await fetch_order(tenant_id, order_id, db)
            if order is None:
                logger.warning("WISMO %s: order %s not found by ID", self.workflow_id, order_id)
                await self.transition("ESCALATED", event, db, reason="order_not_found")
                await self._resolve_if_terminal(db)
                return

            await update_workflow_order(db, self.workflow_id, order_id)
            await self.transition("RETRIEVING_SHIPMENT", event, db, reason=f"order_{order_id}_found_by_id")
        else:
            orders = await find_orders_by_customer(tenant_id, customer_id, db)
            if not orders:
                logger.warning("WISMO %s: no orders for customer %s", self.workflow_id, customer_id)
                await self.transition("ESCALATED", event, db, reason="no_orders_found")
                await self._resolve_if_terminal(db)
                return
            if len(orders) == 1:
                order_id = str(orders[0].get("id", ""))
                if not order_id:
                    await self.transition("ESCALATED", event, db, reason="order_has_no_id")
                    await self._resolve_if_terminal(db)
                    return
                order = await fetch_order(tenant_id, order_id, db)
                if order is None:
                    await self.transition("ESCALATED", event, db, reason="order_fetch_failed")
                    await self._resolve_if_terminal(db)
                    return
                await update_workflow_order(db, self.workflow_id, order_id)
                await self.transition("RETRIEVING_SHIPMENT", event, db, reason=f"order_{order_id}_single_order")
            else:
                await self.transition("WAITING_ORDER_SELECTION", event, db, reason=f"{len(orders)}_orders_found")
                await self._ask_which_order(event, db, orders)
                return

        try:
            fulfillments = await fetch_fulfillments(tenant_id, order_id, db)
        except Exception:
            logger.exception("WISMO %s: fetch_fulfillments failed", self.workflow_id)
            fulfillments = []

        await self._classify_and_respond(event, db, order, fulfillments)

    async def _handle_order_selection(self, event: CanonicalEvent, db: Session) -> None:
        payload = event.payload or {}
        message = payload.get("message", "")
        history = payload.get("history", [])
        customer_id = payload.get("customer_id", self.customer_id)
        tenant_id = UUID(event.tenant_id)

        from .wismo_service import fetch_order, fetch_fulfillments, parse_order_number, update_workflow_order

        parsed = parse_order_number(message) if message else None

        if not parsed and history:
            import re
            last_assistant = None
            for entry in reversed(history):
                if entry.get("role") == "assistant":
                    last_assistant = entry.get("content", "")
                    break
            if last_assistant:
                listed_ids = re.findall(r'\d+\.\s*#?(\d+)', last_assistant)
                if listed_ids:
                    idx_match = re.match(r'^\s*(\d+)\s*$', message)
                    if idx_match:
                        idx = int(idx_match.group(1))
                        if 1 <= idx <= len(listed_ids):
                            parsed = listed_ids[idx - 1]

        if not parsed:
            from ...models import ChatLog
            retry = ChatLog(
                tenant_id=self.tenant_id,
                user_id=customer_id,
                direction="outgoing",
                response=(
                    "I'm sorry, I couldn't find that order number. "
                    "Please tell me the order number (e.g., #1234) so I can look it up."
                ),
                channel="web_widget",
            )
            db.add(retry)
            db.commit()
            return

        order_id = parsed
        order = await fetch_order(tenant_id, order_id, db)
        if order is None:
            from ...models import ChatLog
            not_found = ChatLog(
                tenant_id=self.tenant_id,
                user_id=customer_id,
                direction="outgoing",
                response=(
                    f"I couldn't find order #{order_id}. "
                    "Please double-check the number and try again."
                ),
                channel="web_widget",
            )
            db.add(not_found)
            db.commit()
            return

        await update_workflow_order(db, self.workflow_id, order_id)
        await self.transition("RETRIEVING_SHIPMENT", event, db, reason=f"order_{order_id}_selected_by_customer")

        try:
            fulfillments = await fetch_fulfillments(tenant_id, order_id, db)
        except Exception:
            logger.exception("WISMO %s: fetch_fulfillments failed", self.workflow_id)
            fulfillments = []

        await self._classify_and_respond(event, db, order, fulfillments)

    async def _ask_which_order(self, event: CanonicalEvent, db: Session, orders: list[dict]) -> None:
        customer_id = event.payload.get("customer_id", self.customer_id) if event.payload else self.customer_id
        lines = ["I found several orders for your account. Which one would you like to check?"]
        for i, o in enumerate(orders[:5], 1):
            name = o.get("name", f"Order #{o.get('id', '')}")
            status = o.get("fulfillment_status", "unfulfilled") or "unfulfilled"
            created = (o.get("created_at", "") or "")[:10]
            lines.append(f"{i}. {name} ({status}) — {created}")
        if len(orders) > 5:
            lines.append(f"...and {len(orders) - 5} more.")
        lines.append("Just reply with the order number (e.g., #1234).")

        from ...models import ChatLog
        outgoing = ChatLog(
            tenant_id=self.tenant_id,
            user_id=customer_id,
            direction="outgoing",
            response="\n".join(lines),
            channel="web_widget",
        )
        db.add(outgoing)
        db.commit()

    async def _classify_and_respond(self, event: CanonicalEvent, db: Session, order: dict, fulfillments: list[dict]) -> None:
        if self.current_state != "RETRIEVING_SHIPMENT":
            await self._resolve_if_terminal(db)
            return

        from ..ai.wismo_classifier import classify_tracking_status

        classification = await classify_tracking_status(fulfillments, order)
        status = classification.get("status", "on_track")
        confidence = classification.get("confidence", 0)

        await self.transition(
            "CLASSIFYING_RISK", event, db,
            reason=f"tracking_{status}_({confidence}%)",
        )

        # Policy: escalate delayed that exceeds threshold
        if status == "delayed":
            delay_days = classification.get("delay_days", 0)
            if delay_days >= self.wismo_policy["escalation_delay_days"]:
                await self.transition("ESCALATED", event, db, reason=f"delayed_{delay_days}d_escalated")
                await self._send_notification(event, db, order, classification)
                await self._resolve_if_terminal(db)
                return

        # Policy: escalate lost immediately
        if status == "lost" and self.wismo_policy["auto_escalate_lost"]:
            await self.transition("ESCALATED", event, db, reason="lost_auto_escalated")
            await self._send_notification(event, db, order, classification)
            await self._resolve_if_terminal(db)
            return

        # Policy: notification threshold — don't notify for low-severity statuses
        threshold = self.wismo_policy["auto_notify_threshold"]
        notify_levels = {"on_track": 0, "delayed": 1, "lost": 2}
        status_level = notify_levels.get(status, -1)
        threshold_level = notify_levels.get(threshold, 1)
        if status_level < threshold_level:
            await self.transition("RESOLVED", event, db, reason=f"{status}_silent_per_policy")
            await self._resolve_if_terminal(db)
            return

        if status in ("delayed", "lost"):
            await self.transition("RESPONSE_SENT", event, db, reason=f"notifying_customer_{status}")
            await self._send_notification(event, db, order, classification)
            await self.transition("RESOLVED", event, db, reason=f"notification_sent_{status}")
        elif status == "on_track":
            await self.transition("RESOLVED", event, db, reason="on_track_no_notification_needed")
        else:
            await self.transition("ESCALATED", event, db, reason=f"unknown_status_{status}")

        await self._resolve_if_terminal(db)

    async def _send_notification(self, event: CanonicalEvent, db: Session, order: dict, classification: dict) -> None:
        from ..ai.wismo_responder import generate_wismo_widget_response
        from ..communications.service import send_communication
        from ...models import ChatLog

        # Policy: auto_notify disabled
        if not self.wismo_policy["auto_notify"]:
            logger.info("WISMO %s: auto_notify disabled by policy", self.workflow_id)
            return

        customer_id = event.payload.get("customer_id", self.customer_id) if event.payload else self.customer_id

        # Policy: max notifications per workflow
        existing = db.query(ChatLog).filter(
            ChatLog.tenant_id == self.tenant_id,
            ChatLog.user_id == customer_id,
            ChatLog.direction == "outgoing",
            ChatLog.channel == "web_widget",
        ).count()
        if existing >= self.wismo_policy["max_notifications_per_workflow"]:
            logger.info("WISMO %s: max notifications (%d/%d) reached", self.workflow_id, existing, self.wismo_policy["max_notifications_per_workflow"])
            return

        allowed = self.wismo_policy["notification_channels"]

        status = classification.get("status", "delayed")
        template_map = {"delayed": "delay_notification", "lost": "lost_package"}
        template_name = template_map.get(status, "delay_notification")

        context = {
            "order_name": order.get("name", ""),
            "customer_name": "there",
            "customer_id": customer_id,
            "tenant_id": event.tenant_id,
            "estimated_delivery": classification.get("estimated_delivery", ""),
            "reason": classification.get("reason", ""),
            "email": order.get("email", order.get("contact_email", "")),
        }

        if "widget" in allowed:
            await send_communication(
                db=db,
                tenant_id=str(self.tenant_id),
                customer_id=customer_id,
                channel="widget",
                template_name=template_name,
                context=context,
                workflow_id=str(self.workflow_id),
            )

            widget_msg = await generate_wismo_widget_response(classification, order)
            if widget_msg:
                outgoing = ChatLog(
                    tenant_id=self.tenant_id,
                    user_id=customer_id,
                    direction="outgoing",
                    response=widget_msg,
                    channel="web_widget",
                )
                db.add(outgoing)

        if "email" in allowed and context.get("email"):
            await send_communication(
                db=db,
                tenant_id=str(self.tenant_id),
                customer_id=customer_id,
                channel="email",
                template_name=template_name,
                context=context,
                workflow_id=str(self.workflow_id),
            )

    async def _resolve_if_terminal(self, db: Session) -> None:
        if self.current_state in WISMO_TERMINAL_STATES:
            self.status = "completed"
            db.commit()
