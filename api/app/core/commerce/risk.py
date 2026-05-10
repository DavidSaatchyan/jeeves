"""Customer risk scoring: aggregates payment history, sentiment, subscription state, escalations."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from .customer import CustomerService
from ...models import (
    ChatLog,
    Escalation,
    Invoice,
    PaymentFailure,
    Subscription,
    Workflow,
)


def compute_customer_risk(customer_id: str, tenant_id, db: Session) -> str:
    """Compute unified risk level (low, medium, high) for a customer.

    Factors:
    - Failed payments in last 30 days
    - Sentiment/frustration trend
    - Active escalations
    - Subscription state (past_due, cancelled)
    - Active workflow failures

    Returns risk_level string and writes it to Customer.risk_level.
    """
    from ...models import Customer
    import uuid

    try:
        cid = uuid.UUID(customer_id) if isinstance(customer_id, str) else customer_id
    except (ValueError, TypeError):
        return "unknown"

    customer = db.query(Customer).filter(Customer.id == cid, Customer.tenant_id == tenant_id).first()
    if not customer:
        return "unknown"

    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    # Failed payments in last 30 days
    failed_payments = (
        db.query(func.count(PaymentFailure.id))
        .filter(
            PaymentFailure.customer_id == cid,
            PaymentFailure.created_at >= thirty_days_ago,
        )
        .scalar()
        or 0
    )

    # Past due or cancelled subscriptions
    bad_subs = (
        db.query(func.count(Subscription.id))
        .filter(
            Subscription.customer_id == cid,
            Subscription.status.in_(["past_due", "cancelled", "unpaid"]),
        )
        .scalar()
        or 0
    )

    # Open escalations
    open_esc = (
        db.query(func.count(Escalation.id))
        .filter(
            Escalation.customer_id == cid,
            Escalation.status == "OPEN",
        )
        .scalar()
        or 0
    )

    # Active but failed workflows
    failed_wf = (
        db.query(func.count(Workflow.id))
        .filter(
            Workflow.customer_id == customer_id,
            Workflow.status == "failed",
        )
        .scalar()
        or 0
    )

    # Frustration score from customer model
    frustration = customer.frustration_score or 0

    score = 0
    if failed_payments > 2:
        score += 3
    elif failed_payments > 0:
        score += 1

    if bad_subs > 0:
        score += 3

    if open_esc > 0:
        score += 2

    if failed_wf > 1:
        score += 2
    elif failed_wf > 0:
        score += 1

    if frustration >= 7:
        score += 2
    elif frustration >= 4:
        score += 1

    risk = "low"
    if score >= 6:
        risk = "high"
    elif score >= 3:
        risk = "medium"

    customer.risk_level = risk
    customer.updated_at = datetime.utcnow()
    db.commit()

    return risk
