from __future__ import annotations

import logging
from datetime import datetime
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class SubscriptionService:
    def __init__(self, db: Session):
        self.db = db

    def upsert(self, tenant_id: str, customer_id: str, external_subscription_id: str, status: str,
               plan_name: str = "", amount: float = 0.0, currency: str = "usd") -> dict:
        row = self.db.execute(
            text("SELECT id FROM subscriptions WHERE tenant_id = :tid AND external_subscription_id = :eid"),
            {"tid": tenant_id, "eid": external_subscription_id},
        ).first()

        now = datetime.utcnow()
        if row:
            self.db.execute(
                text("""
                    UPDATE subscriptions SET status = :status, plan_name = :plan, amount = :amt,
                        currency = :cur, updated_at = :now
                    WHERE id = :id
                """),
                {"status": status, "plan": plan_name, "amt": amount, "cur": currency,
                 "now": now, "id": row[0]},
            )
            self.db.commit()
            return {"id": str(row[0]), "external_subscription_id": external_subscription_id, "status": status}

        sid = uuid4()
        self.db.execute(
            text("""
                INSERT INTO subscriptions (id, tenant_id, customer_id, external_subscription_id, status,
                    plan_name, amount, currency, created_at, updated_at)
                VALUES (:id, :tid, :cid, :eid, :status, :plan, :amt, :cur, :now, :now)
            """),
            {"id": sid, "tid": tenant_id, "cid": customer_id, "eid": external_subscription_id,
             "status": status, "plan": plan_name, "amt": amount, "cur": currency, "now": now},
        )
        self.db.commit()
        return {"id": str(sid), "external_subscription_id": external_subscription_id, "status": status}

    def get_by_external_id(self, external_subscription_id: str) -> dict | None:
        row = self.db.execute(
            text("SELECT id, tenant_id, customer_id, external_subscription_id, status, plan_name, amount, currency "
                 "FROM subscriptions WHERE external_subscription_id = :eid"),
            {"eid": external_subscription_id},
        ).first()
        if not row:
            return None
        return {
            "id": str(row[0]), "tenant_id": row[1], "customer_id": row[2],
            "external_subscription_id": row[3], "status": row[4], "plan_name": row[5],
            "amount": row[6], "currency": row[7],
        }

    def is_active(self, external_subscription_id: str) -> bool:
        sub = self.get_by_external_id(external_subscription_id)
        return sub is not None and sub["status"] == "active"
