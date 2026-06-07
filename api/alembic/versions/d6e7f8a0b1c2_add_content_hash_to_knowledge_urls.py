"""add content_hash column to knowledge_urls

Revision ID: d6e7f8a0b1c2
Revises: c1d2e3f4a5b6
Create Date: 2026-06-07 16:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "d6e7f8a0b1c2"
down_revision: str | None = "c1d2e3f4a5b6"
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
    if _has_table("knowledge_urls") and not _has_column("knowledge_urls", "content_hash"):
        op.add_column(
            "knowledge_urls",
            sa.Column("content_hash", sa.String(64), nullable=True),
        )


def downgrade() -> None:
    if _has_table("knowledge_urls") and _has_column("knowledge_urls", "content_hash"):
        op.drop_column("knowledge_urls", "content_hash")
