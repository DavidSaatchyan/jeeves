"""add size_bytes column to knowledge_urls

Revision ID: b4c5d6e7f8a0
Revises: a9b8c7d6e5f4
Create Date: 2026-06-04 10:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "b4c5d6e7f8a0"
down_revision: str | None = "a9b8c7d6e5f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(name: str) -> bool:
    conn = op.get_bind()
    inspector = inspect(conn)
    return name in inspector.get_table_names()


def _has_column(table: str, column: str) -> bool:
    conn = op.get_bind()
    inspector = inspect(conn)
    if not _has_table(table):
        return False
    cols = [c["name"] for c in inspector.get_columns(table)]
    return column in cols


def upgrade() -> None:
    if _has_table("knowledge_urls") and not _has_column("knowledge_urls", "size_bytes"):
        op.add_column(
            "knowledge_urls",
            sa.Column("size_bytes", sa.Integer(), server_default=sa.text("0"), nullable=False),
        )


def downgrade() -> None:
    if _has_table("knowledge_urls") and _has_column("knowledge_urls", "size_bytes"):
        op.drop_column("knowledge_urls", "size_bytes")
