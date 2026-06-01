"""add appointment_cache table for pass-through architecture

Revision ID: b2c3d4e5f6a7
Revises: faa41bd54658
Create Date: 2026-06-01 10:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'faa41bd54658'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Create appointment_cache table (minimal operational cache)
    op.create_table('appointment_cache',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('patient_id', sa.UUID(), nullable=False),
        sa.Column('external_id', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=True, server_default='scheduled'),
        sa.Column('slot_token', sa.String(length=64), nullable=True),
        sa.Column('reminder_sent_24h', sa.Boolean(), nullable=True, server_default=sa.text('0')),
        sa.Column('reminder_sent_2h', sa.Boolean(), nullable=True, server_default=sa.text('0')),
        sa.Column('consent_id', sa.UUID(), nullable=True),
        sa.Column('source', sa.String(length=32), nullable=True, server_default='whatsapp'),
        sa.Column('cached_at', sa.DateTime(), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_appointment_cache_tenant_id', 'appointment_cache', ['tenant_id'])
    op.create_index('ix_appointment_cache_patient_id', 'appointment_cache', ['patient_id'])
    op.create_index('ix_appointment_cache_external_id', 'appointment_cache', ['external_id'])

    # 2. Copy operational fields from appointments to appointment_cache
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT id, tenant_id, patient_id, external_id, status, slot_token, "
                "reminder_sent_24h, reminder_sent_2h, consent_id, source, "
                "created_at, updated_at FROM appointments")
    ).fetchall()
    for row in result:
        conn.execute(
            sa.text(
                "INSERT INTO appointment_cache "
                "(id, tenant_id, patient_id, external_id, status, slot_token, "
                "reminder_sent_24h, reminder_sent_2h, consent_id, source, "
                "cached_at, last_synced_at, created_at, updated_at) "
                "VALUES (:id, :tenant_id, :patient_id, :external_id, :status, :slot_token, "
                ":reminder_sent_24h, :reminder_sent_2h, :consent_id, :source, "
                ":cached_at, :last_synced_at, :created_at, :updated_at)"
            ),
            {
                "id": row[0],
                "tenant_id": row[1],
                "patient_id": row[2],
                "external_id": row[3] or "",
                "status": row[4],
                "slot_token": row[5],
                "reminder_sent_24h": row[6],
                "reminder_sent_2h": row[7],
                "consent_id": row[8],
                "source": row[9],
                "cached_at": row[10],
                "last_synced_at": row[10],
                "created_at": row[10],
                "updated_at": row[11],
            }
        )

    # 3. Rename old appointments table to appointments_archive (non-destructive)
    op.rename_table('appointments', 'appointments_archive')


def downgrade() -> None:
    """Downgrade schema."""
    op.rename_table('appointments_archive', 'appointments')
    op.drop_table('appointment_cache')
