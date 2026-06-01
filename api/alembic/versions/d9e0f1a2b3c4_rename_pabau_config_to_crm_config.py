"""rename pabau_config→crm_config + add crm_provider to tenants

Revision ID: d9e0f1a2b3c4
Revises: d8e9f0a1b2c3
Create Date: 2026-06-01 15:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'd9e0f1a2b3c4'
down_revision: Union[str, Sequence[str], None] = 'd8e9f0a1b2c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [c["name"] for c in inspector.get_columns(table)]
    return column in columns


def upgrade() -> None:
    """Migrate pabau_config → crm_config on tenants table."""
    # Add new columns if they don't exist yet
    if not _has_column("tenants", "crm_config"):
        op.add_column("tenants", sa.Column("crm_config", sa.JSON(), nullable=True))
    if not _has_column("tenants", "crm_provider"):
        op.add_column("tenants", sa.Column("crm_provider", sa.String(length=50), nullable=False, server_default="pabau"))

    # Copy data from old column if it exists
    if _has_column("tenants", "pabau_config"):
        conn = op.get_bind()
        conn.execute(
            sa.text(
                "UPDATE tenants SET crm_config = pabau_config, crm_provider = 'pabau' "
                "WHERE pabau_config IS NOT NULL AND crm_config IS NULL"
            )
        )
        op.drop_column("tenants", "pabau_config")


def downgrade() -> None:
    """Reverse: restore pabau_config, drop crm_provider and crm_config."""
    if not _has_column("tenants", "pabau_config"):
        op.add_column("tenants", sa.Column("pabau_config", sa.JSON(), nullable=True))
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE tenants SET pabau_config = crm_config "
            "WHERE crm_config IS NOT NULL AND pabau_config IS NULL"
        )
    )
    if _has_column("tenants", "crm_provider"):
        op.drop_column("tenants", "crm_provider")
    if _has_column("tenants", "crm_config"):
        op.drop_column("tenants", "crm_config")
