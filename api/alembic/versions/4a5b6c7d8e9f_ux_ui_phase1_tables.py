"""Add UX/UI Phase 1 tables: approval_requests, notification_preferences

Revision ID: 4a5b6c7d8e9f
Revises: 3c4d5e6f7a8b
Create Date: 2026-05-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '4a5b6c7d8e9f'
down_revision: Union[str, Sequence[str], None] = '3c4d5e6f7a8b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'approval_requests',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('workflow_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('workflows.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('customer_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('customers.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('action_type', sa.String(64), nullable=False),
        sa.Column('action_value', postgresql.JSONB(), server_default='{}'),
        sa.Column('reason', sa.Text()),
        sa.Column('expected_outcome', sa.Text()),
        sa.Column('risk_level', sa.String(16), server_default='medium'),
        sa.Column('ai_confidence', sa.Integer(), server_default='0'),
        sa.Column('status', sa.String(32), nullable=False, server_default='PENDING'),
        sa.Column('reviewed_by', sa.Text()),
        sa.Column('reviewed_at', sa.DateTime()),
        sa.Column('policy_reference', sa.Text()),
        sa.Column('simulation_result', postgresql.JSONB(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_approval_requests_tenant', 'approval_requests', ['tenant_id'])
    op.create_index('ix_approval_requests_tenant_status', 'approval_requests', ['tenant_id', 'status'])

    op.create_table(
        'notification_preferences',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, unique=True, index=True),
        sa.Column('escalation_alerts', sa.Boolean(), server_default='true'),
        sa.Column('approval_alerts', sa.Boolean(), server_default='true'),
        sa.Column('workflow_failure_alerts', sa.Boolean(), server_default='true'),
        sa.Column('daily_summary', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_notification_preferences_tenant', 'notification_preferences', ['tenant_id'])


def downgrade() -> None:
    op.drop_table('notification_preferences')
    op.drop_table('approval_requests')
