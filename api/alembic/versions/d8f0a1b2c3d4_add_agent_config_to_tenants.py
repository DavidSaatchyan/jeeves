"""add agent_config column to tenants

Revision ID: d8f0a1b2c3d4
Revises: e1f2a3b4c5d6
Create Date: 2026-06-02 14:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "d8f0a1b2c3d4"
down_revision: str | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    conn = op.get_bind()
    inspector = inspect(conn)
    cols = [c["name"] for c in inspector.get_columns(table)]
    return column in cols


def upgrade() -> None:
    if _has_column("tenants", "agent_config"):
        return
    try:
        op.add_column(
            "tenants",
            sa.Column("agent_config", JSONB(astext_type=sa.Text()), nullable=True),
        )
    except Exception:
        if not _has_column("tenants", "agent_config"):
            raise


def downgrade() -> None:
    if _has_column("tenants", "agent_config"):
        op.drop_column("tenants", "agent_config")
