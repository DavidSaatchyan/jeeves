"""add config, last_sync_at, webhook_secret to crm_connections

Revision ID: c7d8e9f0a1b2
Revises: b2c3d4e5f6a7
Create Date: 2026-06-01 12:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add crm_connection columns that were introduced in Phase 2 migration
    but never applied to production DB (faa41bd54658 was stamped without
    running DROP+CREATE on existing crm_connections table).
    """
    op.add_column('crm_connections', sa.Column('config', sa.JSON(), nullable=True))
    op.add_column('crm_connections', sa.Column('last_sync_at', sa.DateTime(), nullable=True))
    op.add_column('crm_connections', sa.Column('webhook_secret', sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove the added columns."""
    op.drop_column('crm_connections', 'webhook_secret')
    op.drop_column('crm_connections', 'last_sync_at')
    op.drop_column('crm_connections', 'config')
