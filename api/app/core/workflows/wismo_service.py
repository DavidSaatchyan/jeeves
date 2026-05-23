from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from ...integrations.shopify.actions import (
    fetch_customer_orders,
    fetch_fulfillments as _fetch_fulfillments,
    fetch_order as _fetch_order,
)

logger = logging.getLogger(__name__)


ORDER_NUMBER_PATTERNS = [
    re.compile(r"#(\d+)"),
    re.compile(r"order\s*[#:]?\s*(\d+)", re.IGNORECASE),
    re.compile(r"ORD[_-]?(\d+)", re.IGNORECASE),
]


def parse_order_number(message: str | None) -> str | None:
    if not message:
        return None
    for pattern in ORDER_NUMBER_PATTERNS:
        m = pattern.search(message)
        if m:
            return m.group(1)
    return None


async def fetch_order(tenant_id: UUID, order_id: str, db: Session) -> dict | None:
    return await _fetch_order(tenant_id, order_id, db)


async def fetch_fulfillments(tenant_id: UUID, order_id: str, db: Session) -> list[dict]:
    return await _fetch_fulfillments(tenant_id, order_id, db)


async def find_orders_by_customer(tenant_id: UUID, customer_id: str, db: Session) -> list[dict]:
    return await fetch_customer_orders(tenant_id, customer_id, db, limit=10)


def get_or_create_wismo(
    db: Session,
    tenant_id: UUID,
    customer_id: str,
    order_id: str = "",
) -> object | None:
    from .registry import get_workflow_class
    from .wismo import WISMO_INITIAL_STATE

    cls = get_workflow_class("wismo")
    if cls is None:
        logger.error("WISMO workflow class not registered")
        return None

    if order_id:
        existing = db.execute(
            text("""
                SELECT id, current_state, status, started_at
                FROM workflows
                WHERE tenant_id = :tid AND customer_id = :cid AND order_id = :oid AND workflow_type = 'wismo'
                  AND status IN ('active', 'paused')
                ORDER BY started_at DESC
                LIMIT 1
            """),
            {"tid": tenant_id, "cid": customer_id, "oid": order_id},
        ).mappings().first()
    else:
        existing = db.execute(
            text("""
                SELECT id, current_state, status, started_at
                FROM workflows
                WHERE tenant_id = :tid AND customer_id = :cid AND workflow_type = 'wismo'
                  AND status IN ('active', 'paused')
                ORDER BY started_at DESC
                LIMIT 1
            """),
            {"tid": tenant_id, "cid": customer_id},
        ).mappings().first()

    if existing is not None:
        return cls(
            workflow_id=existing["id"],
            tenant_id=tenant_id,
            customer_id=customer_id,
            workflow_type="wismo",
            current_state=existing["current_state"],
            status=existing["status"],
            started_at=existing["started_at"],
        )

    wid = uuid4()
    now = datetime.utcnow()
    expiration = now + timedelta(days=30)

    db.execute(
        text("""
            INSERT INTO workflows (id, tenant_id, customer_id, order_id, workflow_type, current_state, status, started_at, expiration_at)
            VALUES (:id, :tid, :cid, :oid, :wt, :state, 'active', :now, :exp)
        """),
        {
            "id": wid,
            "tid": tenant_id,
            "cid": customer_id,
            "oid": order_id or None,
            "wt": "wismo",
            "state": WISMO_INITIAL_STATE,
            "now": now,
            "exp": expiration,
        },
    )
    db.commit()

    return cls(
        workflow_id=wid,
        tenant_id=tenant_id,
        customer_id=customer_id,
        workflow_type="wismo",
        current_state=WISMO_INITIAL_STATE,
        status="active",
        started_at=now,
    )


async def update_workflow_order(db: Session, workflow_id: UUID, order_id: str) -> None:
    db.execute(
        text("UPDATE workflows SET order_id = :oid WHERE id = :wid"),
        {"oid": order_id, "wid": workflow_id},
    )
    db.commit()
