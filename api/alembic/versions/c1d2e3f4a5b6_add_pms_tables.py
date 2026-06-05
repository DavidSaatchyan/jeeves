"""add pms_services, pms_practitioners, pms_clinic tables

Revision ID: c1d2e3f4a5b6
Revises: b4c5d6e7f8a0
Create Date: 2026-06-05 12:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "b4c5d6e7f8a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(name: str) -> bool:
    conn = op.get_bind()
    inspector = inspect(conn)
    return name in inspector.get_table_names()


def upgrade() -> None:
    if not _has_table("pms_services"):
        op.create_table("pms_services",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("tenant_id", sa.UUID(), nullable=False),
            sa.Column("external_id", sa.Text(), nullable=False, index=True),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("description", sa.Text(), server_default="", nullable=False),
            sa.Column("price_cents", sa.Integer(), server_default=sa.text("0"), nullable=False),
            sa.Column("duration_minutes", sa.Integer(), nullable=True),
            sa.Column("category", sa.Text(), server_default="", nullable=False),
            sa.Column("telehealth_enabled", sa.Boolean(), server_default=sa.text("0"), nullable=False),
            sa.Column("online_bookable", sa.Boolean(), server_default=sa.text("1"), nullable=False),
            sa.Column("raw_data", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_pms_services_tenant_id"), "pms_services", ["tenant_id"], unique=False)

    if not _has_table("pms_practitioners"):
        op.create_table("pms_practitioners",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("tenant_id", sa.UUID(), nullable=False),
            sa.Column("external_id", sa.Text(), nullable=False, index=True),
            sa.Column("display_name", sa.Text(), nullable=False),
            sa.Column("title", sa.Text(), server_default="", nullable=False),
            sa.Column("designation", sa.Text(), server_default="", nullable=False),
            sa.Column("description", sa.Text(), server_default="", nullable=False),
            sa.Column("active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
            sa.Column("raw_data", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_pms_practitioners_tenant_id"), "pms_practitioners", ["tenant_id"], unique=False)

    if not _has_table("pms_clinic"):
        op.create_table("pms_clinic",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("tenant_id", sa.UUID(), nullable=False),
            sa.Column("external_id", sa.Text(), nullable=False),
            sa.Column("business_name", sa.Text(), nullable=False),
            sa.Column("address", sa.Text(), server_default="", nullable=False),
            sa.Column("city", sa.Text(), server_default="", nullable=False),
            sa.Column("state", sa.Text(), server_default="", nullable=False),
            sa.Column("postcode", sa.Text(), server_default="", nullable=False),
            sa.Column("country", sa.Text(), server_default="", nullable=False),
            sa.Column("phone", sa.Text(), server_default="", nullable=False),
            sa.Column("email", sa.Text(), server_default="", nullable=False),
            sa.Column("website", sa.Text(), server_default="", nullable=False),
            sa.Column("timezone", sa.Text(), server_default="", nullable=False),
            sa.Column("raw_data", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_pms_clinic_tenant_id"), "pms_clinic", ["tenant_id"], unique=False)


def downgrade() -> None:
    if _has_table("pms_clinic"):
        op.drop_table("pms_clinic")
    if _has_table("pms_practitioners"):
        op.drop_table("pms_practitioners")
    if _has_table("pms_services"):
        op.drop_table("pms_services")
