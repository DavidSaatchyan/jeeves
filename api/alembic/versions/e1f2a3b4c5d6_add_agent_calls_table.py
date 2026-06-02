"""add agent_calls table for agent framework invocation records

Revision ID: e1f2a3b4c5d6
Revises: d9e0f1a2b3c4
Create Date: 2026-06-02 12:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'd9e0f1a2b3c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table: str) -> bool:
    conn = op.get_bind()
    inspector = inspect(conn)
    return table in inspector.get_table_names()


def upgrade() -> None:
    """Create agent_calls table."""
    if _has_table("agent_calls"):
        return

    op.create_table(
        "agent_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("customer_id", sa.Text(), nullable=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id"), nullable=True),
        sa.Column("channel", sa.String(32), server_default="whatsapp"),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("intent", sa.String(64), nullable=True),
        sa.Column("response", sa.Text(), nullable=True),
        sa.Column("escalate", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("actions", sa.JSON(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_index("ix_agent_calls_tenant_id", "agent_calls", ["tenant_id"])
    op.create_index("ix_agent_calls_conversation_id", "agent_calls", ["conversation_id"])


def downgrade() -> None:
    """Drop agent_calls table."""
    if _has_table("agent_calls"):
        op.drop_table("agent_calls")
