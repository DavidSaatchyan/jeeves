from __future__ import annotations

import logging
from datetime import datetime
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class InvoiceService:
    def __init__(self, db: Session):
        self.db = db

    def upsert(self, tenant_id: str, customer_id: str, external_invoice_id: str, status: str,
               amount_due: float = 0.0, currency: str = "usd", due_date: datetime | None = None) -> dict:
        row = self.db.execute(
            text("SELECT id FROM invoices WHERE tenant_id = :tid AND external_invoice_id = :eid"),
            {"tid": tenant_id, "eid": external_invoice_id},
        ).first()

        now = datetime.utcnow()
        if row:
            self.db.execute(
                text("""
                    UPDATE invoices SET status = :status, amount_due = :amt, currency = :cur,
                        due_date = :due, updated_at = :now
                    WHERE id = :id
                """),
                {"status": status, "amt": amount_due, "cur": currency, "due": due_date,
                 "now": now, "id": row[0]},
            )
            self.db.commit()
            return {"id": str(row[0]), "external_invoice_id": external_invoice_id, "status": status}

        iid = uuid4()
        self.db.execute(
            text("""
                INSERT INTO invoices (id, tenant_id, customer_id, external_invoice_id, status,
                    amount_due, currency, due_date, created_at, updated_at)
                VALUES (:id, :tid, :cid, :eid, :status, :amt, :cur, :due, :now, :now)
            """),
            {"id": iid, "tid": tenant_id, "cid": customer_id, "eid": external_invoice_id,
             "status": status, "amt": amount_due, "cur": currency, "due": due_date, "now": now},
        )
        self.db.commit()
        return {"id": str(iid), "external_invoice_id": external_invoice_id, "status": status}

    def get_by_external_id(self, external_invoice_id: str) -> dict | None:
        row = self.db.execute(
            text("SELECT id, tenant_id, customer_id, external_invoice_id, status, amount_due, currency, due_date "
                 "FROM invoices WHERE external_invoice_id = :eid"),
            {"eid": external_invoice_id},
        ).first()
        if not row:
            return None
        return {
            "id": str(row[0]), "tenant_id": row[1], "customer_id": row[2],
            "external_invoice_id": row[3], "status": row[4], "amount_due": row[5],
            "currency": row[6], "due_date": row[7],
        }

    def is_unpaid(self, external_invoice_id: str) -> bool:
        inv = self.get_by_external_id(external_invoice_id)
        return inv is not None and inv["status"] in ("open", "unpaid")


class PaymentFailureService:
    def __init__(self, db: Session):
        self.db = db

    def record(self, tenant_id: str, invoice_id: str, failure_reason: str,
               failure_code: str = "", attempt_count: int = 1) -> dict:
        pfid = uuid4()
        now = datetime.utcnow()
        self.db.execute(
            text("""
                INSERT INTO payment_failures (id, tenant_id, invoice_id, failure_reason, failure_code,
                    attempt_count, created_at)
                VALUES (:id, :tid, :iid, :reason, :code, :attempt, :now)
            """),
            {"id": pfid, "tid": tenant_id, "iid": invoice_id, "reason": failure_reason,
             "code": failure_code, "attempt": attempt_count, "now": now},
        )
        self.db.commit()
        return {"id": str(pfid), "invoice_id": invoice_id, "failure_reason": failure_reason}

    def get_failures_for_invoice(self, invoice_id: str) -> list[dict]:
        rows = self.db.execute(
            text("SELECT id, failure_reason, failure_code, attempt_count, created_at "
                 "FROM payment_failures WHERE invoice_id = :iid ORDER BY created_at DESC"),
            {"iid": invoice_id},
        ).fetchall()
        return [
            {"id": str(r[0]), "failure_reason": r[1], "failure_code": r[2],
             "attempt_count": r[3], "created_at": r[4]}
            for r in rows
        ]
