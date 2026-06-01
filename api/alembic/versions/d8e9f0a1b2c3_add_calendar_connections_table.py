"""add calendar_connections table for Google Calendar OAuth

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-06-01 14:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8e9f0a1b2c3'
down_revision: Union[str, Sequence[str], None] = 'c7d8e9f0a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create calendar_connections table."""
    op.create_table('calendar_connections',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('provider', sa.String(length=32), nullable=False),
        sa.Column('access_token', sa.Text(), nullable=False),
        sa.Column('refresh_token', sa.Text(), nullable=True),
        sa.Column('token_expiry', sa.DateTime(), nullable=True),
        sa.Column('calendar_id', sa.String(length=256), nullable=True),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='disconnected'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_calendar_connections_tenant_id', 'calendar_connections', ['tenant_id'])


def downgrade() -> None:
    """Drop calendar_connections table."""
    op.drop_table('calendar_connections')
