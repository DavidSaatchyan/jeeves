"""Enrich Customer model with profile and activity columns

Revision ID: f6a7b8c9d0e1
Revises: e5d684ab1c2d
Create Date: 2026-05-24 14:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5d684ab1c2d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('customers', sa.Column('display_name', sa.Text(), nullable=True))
    op.add_column('customers', sa.Column('avatar_url', sa.Text(), nullable=True))
    op.add_column('customers', sa.Column('locale', sa.String(16), nullable=True))
    op.add_column('customers', sa.Column('timezone', sa.String(64), nullable=True))
    op.add_column('customers', sa.Column('tags', postgresql.JSONB(), nullable=True, server_default='[]'))
    op.add_column('customers', sa.Column('total_conversations', sa.Integer(), server_default='0'))
    op.add_column('customers', sa.Column('total_workflows', sa.Integer(), server_default='0'))
    op.add_column('customers', sa.Column('last_message_at', sa.DateTime(), nullable=True))
    op.add_column('customers', sa.Column('sentiment_trend', sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column('customers', 'display_name')
    op.drop_column('customers', 'avatar_url')
    op.drop_column('customers', 'locale')
    op.drop_column('customers', 'timezone')
    op.drop_column('customers', 'tags')
    op.drop_column('customers', 'total_conversations')
    op.drop_column('customers', 'total_workflows')
    op.drop_column('customers', 'last_message_at')
    op.drop_column('customers', 'sentiment_trend')
