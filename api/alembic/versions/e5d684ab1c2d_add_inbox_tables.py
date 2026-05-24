"""Add inbox tables: conversations, messages, operator_notes

Revision ID: e5d684ab1c2d
Revises: d1e2f3a4b5c6
Create Date: 2026-05-24 13:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e5d684ab1c2d'
down_revision: Union[str, Sequence[str], None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'conversations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False, index=True),
        sa.Column('customer_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('customers.id'), nullable=True, index=True),
        sa.Column('user_id', sa.Text(), nullable=False, index=True),
        sa.Column('user_display_name', sa.Text(), nullable=True),
        sa.Column('channel', sa.String(32), nullable=False, server_default='web_widget'),
        sa.Column('status', sa.String(32), nullable=False, server_default='active', index=True),
        sa.Column('assigned_to', sa.Text(), nullable=True),
        sa.Column('assigned_at', sa.DateTime(), nullable=True),
        sa.Column('workflow_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('workflows.id'), nullable=True),
        sa.Column('workflow_type', sa.String(64), nullable=True),
        sa.Column('escalation_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('escalations.id'), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('last_message_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), index=True),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('last_message_preview', sa.Text(), nullable=True),
        sa.Column('message_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unread_count', sa.Integer(), nullable=False, server_default='0'),
    )
    op.create_index('ix_conversations_tenant_status', 'conversations', ['tenant_id', 'status'])
    op.create_index('ix_conversations_tenant_user', 'conversations', ['tenant_id', 'user_id'])

    op.create_table(
        'messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False, index=True),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('conversations.id'), nullable=False, index=True),
        sa.Column('direction', sa.String(16), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('content_type', sa.String(32), server_default='text'),
        sa.Column('sender_type', sa.String(16), nullable=False, server_default='customer'),
        sa.Column('operator_id', sa.Text(), nullable=True),
        sa.Column('workflow_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('workflows.id'), nullable=True),
        sa.Column('workflow_state', sa.String(64), nullable=True),
        sa.Column('sources', postgresql.JSONB(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('delivered', sa.Boolean(), server_default='false'),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), index=True),
    )
    op.create_index('ix_messages_conversation_created', 'messages', ['conversation_id', 'created_at'])

    op.create_table(
        'operator_notes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False, index=True),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('conversations.id'), nullable=False, index=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('operator_id', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('operator_notes')
    op.drop_table('messages')
    op.drop_table('conversations')
