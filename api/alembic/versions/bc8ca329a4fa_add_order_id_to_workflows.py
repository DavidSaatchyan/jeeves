"""add_order_id_to_workflows

Revision ID: bc8ca329a4fa
Revises: bb8645c02f81
Create Date: 2026-05-23 19:24:45.786694

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'bc8ca329a4fa'
down_revision: Union[str, Sequence[str], None] = 'bb8645c02f81'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('workflows', sa.Column('order_id', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('workflows', 'order_id')
