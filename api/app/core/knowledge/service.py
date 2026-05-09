from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class KnowledgeService:
    def __init__(self, db: Session):
        self.db = db

    def search_faq(self, query: str, tenant_id: str, limit: int = 5) -> list[dict[str, Any]]:
        rows = self.db.execute(
            text("""
                SELECT id, question, answer, category
                FROM faq_entries
                WHERE tenant_id = :tid
                  AND (question ILIKE :q OR answer ILIKE :q OR category ILIKE :q)
                LIMIT :lim
            """),
            {"tid": tenant_id, "q": f"%{query}%", "lim": limit},
        ).fetchall()
        return [
            {"id": str(r[0]), "question": r[1], "answer": r[2], "category": r[3]}
            for r in rows
        ]

    def get_faq_by_category(self, tenant_id: str, category: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            text("SELECT id, question, answer, category FROM faq_entries WHERE tenant_id = :tid AND category = :cat"),
            {"tid": tenant_id, "cat": category},
        ).fetchall()
        return [
            {"id": str(r[0]), "question": r[1], "answer": r[2], "category": r[3]}
            for r in rows
        ]

    def add_faq(self, tenant_id: str, question: str, answer: str, category: str = "general") -> dict[str, Any]:
        from uuid import uuid4
        from datetime import datetime

        fid = uuid4()
        self.db.execute(
            text("""
                INSERT INTO faq_entries (id, tenant_id, question, answer, category, created_at)
                VALUES (:id, :tid, :q, :a, :cat, :now)
            """),
            {"id": fid, "tid": tenant_id, "q": question, "a": answer, "cat": category, "now": datetime.utcnow()},
        )
        self.db.commit()
        return {"id": str(fid), "question": question, "answer": answer, "category": category}

    def delete_faq(self, faq_id: str) -> bool:
        self.db.execute(text("DELETE FROM faq_entries WHERE id = :id"), {"id": faq_id})
        self.db.commit()
        return True
