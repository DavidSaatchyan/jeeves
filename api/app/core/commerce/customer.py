from __future__ import annotations

import logging
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class CustomerService:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create(self, tenant_id: str, external_id: str, email: str = "", name: str = "") -> dict:
        row = self.db.execute(
            text("SELECT id, tenant_id, external_id, email, name FROM customers WHERE tenant_id = :tid AND external_id = :eid"),
            {"tid": tenant_id, "eid": external_id},
        ).first()

        if row:
            return {"id": str(row[0]), "tenant_id": row[1], "external_id": row[2], "email": row[3], "name": row[4]}

        cid = uuid4()
        self.db.execute(
            text("""
                INSERT INTO customers (id, tenant_id, external_id, email, name)
                VALUES (:id, :tid, :eid, :email, :name)
            """),
            {"id": cid, "tid": tenant_id, "eid": external_id, "email": email, "name": name},
        )
        self.db.commit()
        return {"id": str(cid), "tenant_id": tenant_id, "external_id": external_id, "email": email, "name": name}

    def get_by_id(self, customer_id: str) -> dict | None:
        row = self.db.execute(
            text("SELECT id, tenant_id, external_id, email, name FROM customers WHERE id = :id"),
            {"id": customer_id},
        ).first()
        if not row:
            return None
        return {"id": str(row[0]), "tenant_id": row[1], "external_id": row[2], "email": row[3], "name": row[4]}

    def update_email(self, customer_id: str, email: str) -> None:
        self.db.execute(
            text("UPDATE customers SET email = :email WHERE id = :id"),
            {"email": email, "id": customer_id},
        )
        self.db.commit()
