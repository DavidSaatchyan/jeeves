"""add last_fetched_at column to knowledge_urls

Revision ID: e7f8a0b1c2d3
Revises: d6e7f8a0b1c2
Create Date: 2026-06-07 16:05:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "e7f8a0b1c2d3"
down_revision: str | None = "d6e7f8a0b1c2"
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
    if _has_table("knowledge_urls") and not _has_column("knowledge_urls", "last_fetched_at"):
        op.add_column(
            "knowledge_urls",
            sa.Column("last_fetched_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    if _has_table("knowledge_urls") and _has_column("knowledge_urls", "last_fetched_at"):
        op.drop_column("knowledge_urls", "last_fetched_at")
