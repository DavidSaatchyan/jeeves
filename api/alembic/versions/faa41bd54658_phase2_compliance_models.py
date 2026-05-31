"""phase2_compliance_models

Revision ID: faa41bd54658
Revises: 37a6ad5f6b73
Create Date: 2026-05-31 17:06:24.921725

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'faa41bd54658'
down_revision: Union[str, Sequence[str], None] = '37a6ad5f6b73'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Patients — add compliance columns
    op.add_column('patients', sa.Column('gender', sa.String(length=16), nullable=True))
    op.add_column('patients', sa.Column('consent_timestamp', sa.DateTime(), nullable=True))
    op.add_column('patients', sa.Column('consent_channel', sa.String(length=32), nullable=True))
    op.add_column('patients', sa.Column('gdpr_data_retention', sa.String(length=32), nullable=True))

    # Appointments
    op.create_table('appointments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('patient_id', sa.UUID(), nullable=False),
        sa.Column('external_id', sa.Text(), nullable=True),
        sa.Column('provider_name', sa.Text(), nullable=False),
        sa.Column('provider_specialty', sa.Text(), nullable=True),
        sa.Column('department', sa.Text(), nullable=True),
        sa.Column('start_time', sa.DateTime(), nullable=False),
        sa.Column('end_time', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='scheduled'),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('source', sa.String(length=32), nullable=True, server_default='whatsapp'),
        sa.Column('slot_token', sa.String(length=64), nullable=True),
        sa.Column('reminder_sent_24h', sa.Boolean(), nullable=True, server_default=sa.text('0')),
        sa.Column('reminder_sent_2h', sa.Boolean(), nullable=True, server_default=sa.text('0')),
        sa.Column('consent_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_appointments_tenant_id'), 'appointments', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_appointments_patient_id'), 'appointments', ['patient_id'], unique=False)

    # Consent logs
    op.create_table('consent_logs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('patient_id', sa.UUID(), nullable=True),
        sa.Column('type', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='granted'),
        sa.Column('channel', sa.String(length=32), nullable=False),
        sa.Column('consent_text', sa.Text(), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('granted_at', sa.DateTime(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_consent_logs_tenant_id'), 'consent_logs', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_consent_logs_patient_id'), 'consent_logs', ['patient_id'], unique=False)
    op.create_index('ix_consent_logs_tenant_type_status', 'consent_logs', ['tenant_id', 'type', 'status'])

    # Providers
    op.create_table('providers',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('external_id', sa.Text(), nullable=True),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('specialty', sa.Text(), nullable=True),
        sa.Column('email', sa.Text(), nullable=True),
        sa.Column('phone', sa.Text(), nullable=True),
        sa.Column('schedule', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_providers_tenant_id'), 'providers', ['tenant_id'], unique=False)

    # CRM connections
    op.create_table('crm_connections',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('provider', sa.String(length=32), nullable=False),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='disconnected'),
        sa.Column('last_sync_at', sa.DateTime(), nullable=True),
        sa.Column('webhook_secret', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_crm_connections_tenant_id'), 'crm_connections', ['tenant_id'], unique=False)

    # Audit logs
    op.create_table('audit_logs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('patient_id', sa.UUID(), nullable=True),
        sa.Column('actor_type', sa.String(length=16), nullable=False),
        sa.Column('actor_id', sa.Text(), nullable=False),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('resource_type', sa.String(length=32), nullable=True),
        sa.Column('resource_id', sa.Text(), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('retention_until', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_logs_tenant_id'), 'audit_logs', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_timestamp'), 'audit_logs', ['timestamp'], unique=False)
    op.create_index('ix_audit_logs_tenant_action', 'audit_logs', ['tenant_id', 'action'])
    op.create_index('ix_audit_logs_tenant_timestamp', 'audit_logs', ['tenant_id', 'timestamp'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('audit_logs')
    op.drop_table('crm_connections')
    op.drop_table('providers')
    op.drop_table('consent_logs')
    op.drop_table('appointments')
    op.drop_column('patients', 'gdpr_data_retention')
    op.drop_column('patients', 'consent_channel')
    op.drop_column('patients', 'consent_timestamp')
    op.drop_column('patients', 'gender')
