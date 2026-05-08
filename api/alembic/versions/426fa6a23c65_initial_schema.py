"""initial_schema

Revision ID: 426fa6a23c65
Revises: 
Create Date: 2026-05-08 10:34:35.145371

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '426fa6a23c65'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        'tenants',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('email', sa.Text(), nullable=False, unique=True),
        sa.Column('hashed_password', sa.Text(), nullable=False),
        sa.Column('email_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('trial_ends', sa.DateTime()),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('dialogs_used', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('resolved_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_tenants_email', 'tenants', ['email'])

    op.create_table(
        'crm_config',
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('provider', sa.String(32), nullable=False, server_default='custom_rest'),
        sa.Column('read_url', sa.Text()),
        sa.Column('write_url', sa.Text()),
        sa.Column('headers', postgresql.JSONB(), server_default='{}'),
        sa.Column('read_mapping', postgresql.JSONB(), server_default='{}'),
        sa.Column('write_mapping', postgresql.JSONB(), server_default='{}'),
        sa.Column('capabilities', postgresql.JSONB(), server_default='{}'),
        sa.Column('primary_identifier', sa.String(32), nullable=False, server_default='email'),
    )

    op.create_table(
        'crm_action_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('action', sa.Text(), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('request', postgresql.JSONB(), server_default='{}'),
        sa.Column('response', postgresql.JSONB()),
        sa.Column('error', sa.Text()),
        sa.Column('latency_ms', sa.Integer()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_crm_action_logs_tenant_id', 'crm_action_logs', ['tenant_id'])
    op.create_index('ix_crm_action_logs_user_id', 'crm_action_logs', ['user_id'])

    op.create_table(
        'crm_connections',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', sa.String(32), nullable=False),
        sa.Column('status', sa.String(16), nullable=False, server_default='connected'),
        sa.Column('access_token', sa.Text(), nullable=False),
        sa.Column('refresh_token', sa.Text(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('account_id', sa.Text()),
        sa.Column('scopes', postgresql.JSONB(), server_default='[]'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_crm_connections_tenant_id', 'crm_connections', ['tenant_id'])
    op.create_index('ix_crm_connections_provider', 'crm_connections', ['provider'])

    op.create_table(
        'proactive_metric',
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('metric_url', sa.Text()),
        sa.Column('threshold', sa.Integer(), server_default='30'),
        sa.Column('last_triggered_per_user', postgresql.JSONB(), server_default='{}'),
    )

    op.create_table(
        'files',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('filename', sa.Text(), nullable=False),
        sa.Column('s3_key', sa.Text()),
        sa.Column('status', sa.String(32), nullable=False, server_default='processing'),
        sa.Column('content_hash', sa.String(64)),
        sa.Column('chunks_total', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('size_bytes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error', sa.Text()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_files_tenant_id', 'files', ['tenant_id'])
    op.create_index('ix_files_content_hash', 'files', ['content_hash'])

    op.create_table(
        'agent_tools',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('tool_type', sa.String(16), nullable=False),
        sa.Column('method', sa.String(8), nullable=False, server_default='GET'),
        sa.Column('url_template', sa.Text(), nullable=False),
        sa.Column('headers', postgresql.JSONB(), server_default='{}'),
        sa.Column('body_template', postgresql.JSONB(), server_default='{}'),
        sa.Column('parameters', postgresql.JSONB(), server_default='{}'),
        sa.Column('require_confirmation', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_agent_tools_tenant', 'agent_tools', ['tenant_id'])

    op.create_table(
        'agent_tool_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tool_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('agent_tools.id', ondelete='SET NULL')),
        sa.Column('tool_name', sa.String(64), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('request', postgresql.JSONB(), server_default='{}'),
        sa.Column('response', postgresql.JSONB()),
        sa.Column('error', sa.Text()),
        sa.Column('latency_ms', sa.Integer()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_agent_tool_logs_tenant', 'agent_tool_logs', ['tenant_id'])
    op.create_index('ix_agent_tool_logs_user_id', 'agent_tool_logs', ['user_id'])

    op.create_table(
        'chat_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('direction', sa.String(16), nullable=False),
        sa.Column('message', sa.Text()),
        sa.Column('response', sa.Text()),
        sa.Column('resolution', sa.String(16)),
        sa.Column('action_called', sa.Text()),
        sa.Column('latency_ms', sa.Integer()),
        sa.Column('delivered', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('sources', postgresql.JSONB()),
        sa.Column('session_id', postgresql.UUID(as_uuid=True)),
        sa.Column('extra_fields', postgresql.JSONB(), server_default='{}'),
        sa.Column('channel', sa.String(32), nullable=False, server_default='web_widget'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_chat_logs_tenant_id', 'chat_logs', ['tenant_id'])
    op.create_index('ix_chat_logs_user_id', 'chat_logs', ['user_id'])
    op.create_index('ix_chat_logs_session_id', 'chat_logs', ['session_id'])

    op.create_table(
        'conversation_ratings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('message_id', postgresql.UUID(as_uuid=True)),
        sa.Column('rating', sa.String(16), nullable=False),
        sa.Column('feedback', sa.Text(), server_default=''),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_conversation_ratings_tenant_id', 'conversation_ratings', ['tenant_id'])
    op.create_index('ix_conversation_ratings_user_id', 'conversation_ratings', ['user_id'])

    op.create_table(
        'native_connectors',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider', sa.String(32), nullable=False),
        sa.Column('status', sa.String(16), nullable=False, server_default='connected'),
        sa.Column('credentials', sa.Text(), nullable=False),
        sa.Column('meta', postgresql.JSONB(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('tenant_id', 'provider', name='uq_native_connectors_tenant_provider'),
    )
    op.create_index('ix_native_connectors_tenant', 'native_connectors', ['tenant_id'])

    op.create_table(
        'webhook_configs',
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('incoming_url', sa.Text()),
        sa.Column('incoming_secret', sa.Text()),
        sa.Column('outgoing_url', sa.Text()),
        sa.Column('outgoing_secret', sa.Text()),
        sa.Column('field_mapping', postgresql.JSONB(), server_default='{}'),
        sa.Column('events', postgresql.JSONB(), server_default='[]'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        'writeback_configs',
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('type', sa.String(32), nullable=False, server_default='off'),
        sa.Column('hubspot_note_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('hubspot_task_on_escalation', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('webhook_url', sa.Text()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        'channels_config',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('channel_type', sa.String(32), nullable=False),
        sa.Column('config', postgresql.JSONB(), server_default='{}'),
        sa.Column('status', sa.String(16), nullable=False, server_default='inactive'),
        sa.Column('last_error', sa.Text()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('tenant_id', 'channel_type', name='uq_channels_config_tenant_type'),
    )
    op.create_index('ix_channels_config_tenant_id', 'channels_config', ['tenant_id'])

    op.create_table(
        'api_keys',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(128), nullable=False),
        sa.Column('key_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('prefix', sa.String(8), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('last_used_at', sa.DateTime()),
        sa.Column('expires_at', sa.DateTime()),
    )
    op.create_index('ix_api_keys_tenant', 'api_keys', ['tenant_id'])
    op.create_index('ix_api_keys_hash', 'api_keys', ['key_hash'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('api_keys')
    op.drop_table('channels_config')
    op.drop_table('writeback_configs')
    op.drop_table('webhook_configs')
    op.drop_table('native_connectors')
    op.drop_table('conversation_ratings')
    op.drop_table('chat_logs')
    op.drop_table('agent_tool_logs')
    op.drop_table('agent_tools')
    op.drop_table('files')
    op.drop_table('proactive_metric')
    op.drop_table('crm_connections')
    op.drop_table('crm_action_logs')
    op.drop_table('crm_config')
    op.drop_table('tenants')
