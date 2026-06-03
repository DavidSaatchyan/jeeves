"""add knowledge_folders, knowledge_urls tables, folder_id to files

Revision ID: a9b8c7d6e5f4
Revises: d8f0a1b2c3d4
Create Date: 2026-06-03 10:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "a9b8c7d6e5f4"
down_revision: str | None = "d8f0a1b2c3d4"
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
    # ── knowledge_folders ──────────────────────────────────────────────────
    if not _has_table("knowledge_folders"):
        op.create_table(
            "knowledge_folders",
            sa.Column("id", UUID(as_uuid=True), primary_key=True, default=sa.text("gen_random_uuid()")),
            sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_folders.id", ondelete="CASCADE"), nullable=True, index=True),
            sa.Column("sort_order", sa.Integer(), server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()")),
            sa.UniqueConstraint("tenant_id", "name", "parent_id", name="uq_knowledge_folder_name_per_parent"),
        )

    # ── knowledge_urls ────────────────────────────────────────────────────
    if not _has_table("knowledge_urls"):
        op.create_table(
            "knowledge_urls",
            sa.Column("id", UUID(as_uuid=True), primary_key=True, default=sa.text("gen_random_uuid()")),
            sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("url", sa.Text(), nullable=False),
            sa.Column("title", sa.Text(), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
            sa.Column("folder_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_folders.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("chunks_total", sa.Integer(), server_default=sa.text("0")),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        )

    # ── folder_id on files ────────────────────────────────────────────────
    if _has_table("files") and not _has_column("files", "folder_id"):
        op.add_column(
            "files",
            sa.Column("folder_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_folders.id", ondelete="SET NULL"), nullable=True, index=True),
        )


def downgrade() -> None:
    if _has_column("files", "folder_id"):
        op.drop_column("files", "folder_id")
    if _has_table("knowledge_urls"):
        op.drop_table("knowledge_urls")
    if _has_table("knowledge_folders"):
        op.drop_table("knowledge_folders")
