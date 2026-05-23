"""add_wismo_policy_to_policyset

Revision ID: d1e2f3a4b5c6
Revises: bc8ca329a4fa
Create Date: 2026-05-23 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, Sequence[str], None] = 'bc8ca329a4fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('policy_sets', sa.Column('wismo_policy', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('policy_sets', 'wismo_policy')
