from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from ..events.schemas import CanonicalEvent
from ..commerce.customer import CustomerService
from ..commerce.subscription import SubscriptionService
from ..commerce.billing import InvoiceService, PaymentFailureService
from ...integrations.stripe.actions import execute_retry_payment, fetch_invoice_state, fetch_customer_data, fetch_payment_method_data
from ...shared.idempotency import idempotency_get
from ...shared.locks import workflow_lock
from ..policies.retry_rules import compute_retry_schedule, is_retry_eligible
from ..ai.classifier import classify_failure
from ..ai.sentiment import detect_frustration
from ..communications.service import send_communication
from ..communications.deduplication import is_duplicate_communication
from ..workflows.scheduler import schedule_job
from .runtime import Workflow
from .registry import register_workflow

logger = logging.getLogger(__name__)


class PaymentRecoveryWorkflow(Workflow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.attempt_count: int = 0
        self.failure_category: str = ""
        self.selected_strategy: dict[str, Any] = {}

    async def handle_event(self, event: CanonicalEvent, db: Session) -> None:
        async with workflow_lock(self.workflow_id) as acquired:
            if not acquired:
                logger.warning("could not acquire lock for workflow %s", self.workflow_id)
                return

            state_handlers = {
                "DETECTED": self._handle_detected,
                "VALIDATING": self._handle_validating,
                "CLASSIFYING_FAILURE": self._handle_classifying_failure,
                "SELECTING_STRATEGY": self._handle_selecting_strategy,
                "OUTREACH_PENDING": self._handle_outreach_pending,
                "OUTREACH_SENT": self._handle_outreach_sent,
                "WAITING_CUSTOMER": self._handle_waiting_customer,
                "RETRY_SCHEDULED": self._handle_retry_scheduled,
                "RETRY_PENDING": self._handle_retry_pending,
                "RETRYING": self._handle_retrying,
                "VERIFYING_RESULT": self._handle_verifying_result,
                "PAUSED_RECONCILIATION": self._handle_paused_reconciliation,
            }

            handler = state_handlers.get(self.current_state)
            if handler:
                await handler(event, db)
            else:
                logger.warning("no handler for state %s", self.current_state)

    async def _handle_detected(self, event: CanonicalEvent, db: Session) -> None:
        await self.transition("VALIDATING", event, db, reason="payment_failure_detected")

    async def _handle_validating(self, event: CanonicalEvent, db: Session) -> None:
        invoice_id = event.entity_id
        customer_id = event.payload.get("customer_id", "")
        subscription_id = event.payload.get("subscription_id", "")

        inv_service = InvoiceService(db)
        invoice = inv_service.get_by_external_id(invoice_id)
        if not invoice:
            invoice = inv_service.upsert(
                tenant_id=event.tenant_id,
                customer_id=customer_id,
                external_invoice_id=invoice_id,
                status="open",
                amount_due=event.payload.get("amount_due", 0),
                currency=event.payload.get("currency", "usd"),
            )

        sub_service = SubscriptionService(db)
        sub = sub_service.get_by_external_id(subscription_id)

        if not is_retry_eligible(
            subscription_active=sub is not None and sub["status"] == "active",
            is_duplicate=False,
            is_escalated=False,
        ):
            logger.info("validation failed: retry not eligible")
            await self.transition("FAILED", event, db, reason="validation_failed")
            return

        await self.transition("CLASSIFYING_FAILURE", event, db, reason="validation_passed")

    async def _handle_classifying_failure(self, event: CanonicalEvent, db: Session) -> None:
        failure_reason = event.payload.get("failure_reason", event.payload.get("raw_type", "unknown"))
        failure_code = event.payload.get("failure_code", "")

        from ...shared.idempotency import idempotency_check

        classification = await classify_failure(failure_reason, failure_code)
        self.failure_category = classification.get("category", "recoverable")

        ai_interaction_id = _record_ai_interaction(
            db=db, tenant_id=event.tenant_id, workflow_id=self.workflow_id,
            input_data={"failure_reason": failure_reason, "failure_code": failure_code},
            output_data=classification,
            interaction_type="failure_classification",
        )

        if classification.get("confidence", 0) < 0.3:
            logger.warning("low confidence classification, escalating")
            await self.transition("ESCALATED", event, db, reason="low_confidence_classification")
            return

        await self.transition("SELECTING_STRATEGY", event, db, reason=f"classified_as_{self.failure_category}")

    async def _handle_selecting_strategy(self, event: CanonicalEvent, db: Session) -> None:
        from ..policies.retry_rules import compute_retry_schedule

        schedule = compute_retry_schedule(
            failure_category=self.failure_category,
            attempt_count=self.attempt_count,
            tenant_id=event.tenant_id,
        )

        self.selected_strategy = schedule
        action = "outreach" if self.failure_category in ("semi_recoverable",) else "retry"

        if action == "outreach":
            await self.transition("OUTREACH_PENDING", event, db, reason="customer_action_needed")
        else:
            await self.transition("RETRY_SCHEDULED", event, db, reason="automatic_retry_scheduled")

    async def _handle_outreach_pending(self, event: CanonicalEvent, db: Session) -> None:
        customer_id = event.payload.get("customer_id", "")
        customer_name = CustomerService(db).get_by_id(customer_id)
        amount = event.payload.get("amount_due", "")

        comm_context = {
            "customer_name": customer_name.get("name", "") if customer_name else "",
            "email": customer_name.get("email", "") if customer_name else "",
            "amount": amount,
            "plan_name": event.payload.get("subscription_id", ""),
        }

        if self.failure_category == "semi_recoverable":
            template_name = "auth_assistance"
        else:
            template_name = "payment_update"

        comm_id = await send_communication(
            db=db,
            tenant_id=event.tenant_id,
            customer_id=customer_id,
            channel="email",
            template_name=template_name,
            context=comm_context,
            workflow_id=str(self.workflow_id),
        )

        if comm_id:
            await self.transition("OUTREACH_SENT", event, db, reason=f"comms_sent_{template_name}")
        else:
            await self.transition("RETRY_SCHEDULED", event, db, reason="comms_failed_skip_to_retry")

    async def _handle_outreach_sent(self, event: CanonicalEvent, db: Session) -> None:
        await self.transition("WAITING_CUSTOMER", event, db, reason="outreach_complete")

    async def _handle_waiting_customer(self, event: CanonicalEvent, db: Session) -> None:
        if event.event_type == "customer_payment_method_updated":
            await self.transition("RETRY_PENDING", event, db, reason="payment_method_updated")
        elif event.event_type == "customer_frustrated":
            frustration = await detect_frustration(event.payload.get("message", ""))
            if frustration.get("level") in ("medium", "high"):
                await self.transition("ESCALATED", event, db, reason="customer_frustrated")
            else:
                logger.info("frustration level low, continuing wait")
        elif event.event_type == "external_payment_success":
            await self.transition("RECOVERED", event, db, reason="external_payment_detected")
        elif event.event_type == "subscription_cancel_requested":
            await self._escalate(event, db, "customer_cancelled_during_recovery")
            return
        elif event.event_type == "workflow_timeout":
            await self.transition("RETRY_SCHEDULED", event, db, reason="wait_timeout_proceed_to_retry")

    async def _handle_retry_scheduled(self, event: CanonicalEvent, db: Session) -> None:
        schedule = self.selected_strategy or compute_retry_schedule(
            failure_category=self.failure_category,
            attempt_count=self.attempt_count,
            tenant_id=event.tenant_id,
        )

        if not schedule.get("should_retry"):
            await self.transition("FAILED", event, db, reason="max_retries_exceeded")
            return

        execute_at = schedule.get("execute_at")
        if isinstance(execute_at, datetime):
            await schedule_job(
                job_type="retry",
                execute_at=execute_at,
                payload={
                    "workflow_id": str(self.workflow_id),
                    "invoice_id": event.entity_id,
                    "attempt": self.attempt_count + 1,
                    "tenant_id": event.tenant_id,
                },
            )

        await self.transition("RETRY_PENDING", event, db, reason=f"retry_scheduled_attempt_{self.attempt_count + 1}")

    async def _handle_retry_pending(self, event: CanonicalEvent, db: Session) -> None:
        await self.transition("RETRYING", event, db, reason="retry_triggered")

    async def _handle_retrying(self, event: CanonicalEvent, db: Session) -> None:
        invoice_id = event.entity_id
        self.attempt_count += 1

        result = await execute_retry_payment(invoice_id, self.attempt_count)
        if result and result.get("status") in ("paid", "succeeded"):
            await self.transition("VERIFYING_RESULT", event, db, reason="retry_attempt_succeeded")
        else:
            _record_payment_failure(
                db=db, tenant_id=event.tenant_id, invoice_id=invoice_id,
                failure_reason=str(result or "payment_failed"),
                attempt_count=self.attempt_count,
            )
            await self.transition("VERIFYING_RESULT", event, db, reason="retry_attempt_failed")

    async def _escalate(self, event: CanonicalEvent, db: Session, reason: str) -> None:
        from ..escalations.manager import EscalationManager
        mgr = EscalationManager(db)
        mgr.create(
            tenant_id=event.tenant_id,
            workflow_id=self.workflow_id,
            reason=reason,
            source="payment_recovery",
        )
        mgr.pause_workflow(self.workflow_id)
        await self.transition("ESCALATED", event, db, reason=reason)

    async def _handle_verifying_result(self, event: CanonicalEvent, db: Session) -> None:
        invoice_id = event.entity_id
        invoice_state = await fetch_invoice_state(invoice_id)

        if not invoice_state:
            await self.transition("ESCALATED", event, db, reason="cannot_verify_invoice_state")
            return

        status = invoice_state.get("status", "")
        if status in ("paid", "succeeded"):
            await self.transition("RECOVERED", event, db, reason="invoice_paid")
        elif status == "open":
            if self.attempt_count >= 3:
                await self.transition("WAITING_CUSTOMER", event, db, reason="retries_exhausted_waiting_customer")
            else:
                await self.transition("RETRY_SCHEDULED", event, db, reason="still_unpaid_retry_again")
        else:
            await self.transition("PAUSED_RECONCILIATION", event, db, reason="state_mismatch_reconciliation")

    async def _handle_paused_reconciliation(self, event: CanonicalEvent, db: Session) -> None:
        invoice_id = event.entity_id
        invoice_state = await fetch_invoice_state(invoice_id)

        if invoice_state and invoice_state.get("status") in ("paid", "succeeded"):
            await self.transition("RECOVERED", event, db, reason="reconciled_paid")
        elif self.attempt_count >= 5:
            await self.transition("FAILED", event, db, reason="reconciliation_failed")
        else:
            await self.transition("VALIDATING", event, db, reason="reconciliation_revalidate")


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


def _record_payment_failure(db: Session, tenant_id: str, invoice_id: str,
                             failure_reason: str, attempt_count: int) -> None:
    PaymentFailureService(db).record(
        tenant_id=tenant_id,
        invoice_id=invoice_id,
        failure_reason=failure_reason,
        attempt_count=attempt_count,
    )


register_workflow("payment_recovery", PaymentRecoveryWorkflow)
