from __future__ import annotations

import logging
from datetime import datetime
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from ...integrations.tracking.normalizer import normalize_carrier_state

logger = logging.getLogger(__name__)


class ShipmentService:
    def __init__(self, db: Session):
        self.db = db

    def upsert(self, tenant_id: str, customer_id: str, order_id: str, tracking_number: str,
               carrier: str = "", status: str = "unknown", estimated_delivery: datetime | None = None) -> dict:
        row = self.db.execute(
            text("SELECT id FROM shipments WHERE tenant_id = :tid AND tracking_number = :tn"),
            {"tid": tenant_id, "tn": tracking_number},
        ).first()

        now = datetime.utcnow()
        canonical_status = normalize_carrier_state(carrier, status)

        if row:
            self.db.execute(
                text("""
                    UPDATE shipments SET status = :status, carrier = :carrier,
                        estimated_delivery = :eta, updated_at = :now
                    WHERE id = :id
                """),
                {"status": canonical_status, "carrier": carrier, "eta": estimated_delivery,
                 "now": now, "id": row[0]},
            )
            self.db.commit()
            return {"id": str(row[0]), "tracking_number": tracking_number, "status": canonical_status}

        sid = uuid4()
        self.db.execute(
            text("""
                INSERT INTO shipments (id, tenant_id, customer_id, order_id, tracking_number,
                    carrier, status, estimated_delivery, created_at, updated_at)
                VALUES (:id, :tid, :cid, :oid, :tn, :carrier, :status, :eta, :now, :now)
            """),
            {"id": sid, "tid": tenant_id, "cid": customer_id, "oid": order_id,
             "tn": tracking_number, "carrier": carrier, "status": canonical_status,
             "eta": estimated_delivery, "now": now},
        )
        self.db.commit()
        return {"id": str(sid), "tracking_number": tracking_number, "status": canonical_status}

    def get_by_order(self, order_id: str) -> list[dict]:
        rows = self.db.execute(
            text("SELECT id, tracking_number, carrier, status, estimated_delivery, created_at "
                 "FROM shipments WHERE order_id = :oid ORDER BY created_at DESC"),
            {"oid": order_id},
        ).fetchall()
        return [
            {"id": str(r[0]), "tracking_number": r[1], "carrier": r[2],
             "status": r[3], "estimated_delivery": r[4], "created_at": r[5]}
            for r in rows
        ]

    def get_by_tracking(self, tracking_number: str) -> dict | None:
        row = self.db.execute(
            text("SELECT id, tenant_id, customer_id, order_id, tracking_number, carrier, status, estimated_delivery "
                 "FROM shipments WHERE tracking_number = :tn"),
            {"tn": tracking_number},
        ).first()
        if not row:
            return None
        return {
            "id": str(row[0]), "tenant_id": row[1], "customer_id": row[2],
            "order_id": row[3], "tracking_number": row[4], "carrier": row[5],
            "status": row[6], "estimated_delivery": row[7],
        }
