"""v2 model column additions (policy_snapshot, template_name, escalation fields)

Revision ID: 3c4d5e6f7a8b
Revises: 2a3b4c5d6e7f
Create Date: 2026-05-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '3c4d5e6f7a8b'
down_revision: Union[str, Sequence[str], None] = '2a3b4c5d6e7f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add missing columns to match updated models.py."""

    # workflow_transitions: add policy_snapshot
    op.add_column(
        'workflow_transitions',
        sa.Column('policy_snapshot', postgresql.JSONB(), server_default='{}'),
    )

    # communications: add template_name
    op.add_column(
        'communications',
        sa.Column('template_name', sa.String(64)),
    )

    # escalations: add assigned_to, source, metadata, sla_breached, updated_at
    op.add_column(
        'escalations',
        sa.Column('assigned_to', sa.Text()),
    )
    op.add_column(
        'escalations',
        sa.Column('source', sa.String(64)),
    )
    op.add_column(
        'escalations',
        sa.Column('metadata', postgresql.JSONB(), server_default='{}'),
    )
    op.add_column(
        'escalations',
        sa.Column('sla_breached', sa.Boolean(), server_default='false'),
    )
    op.add_column(
        'escalations',
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    """Remove columns added in upgrade."""
    op.drop_column('workflow_transitions', 'policy_snapshot')
    op.drop_column('communications', 'template_name')
    op.drop_column('escalations', 'assigned_to')
    op.drop_column('escalations', 'source')
    op.drop_column('escalations', 'metadata')
    op.drop_column('escalations', 'sla_breached')
    op.drop_column('escalations', 'updated_at')
