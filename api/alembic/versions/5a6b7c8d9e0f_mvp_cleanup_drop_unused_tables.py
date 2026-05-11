"""Drop tables removed in MVP cleanup: orders, shipments, writeback_configs, approval_requests

Revision ID: 5a6b7c8d9e0f
Revises: 4a5b6c7d8e9f
Create Date: 2026-05-11 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '5a6b7c8d9e0f'
down_revision: Union[str, Sequence[str], None] = '4a5b6c7d8e9f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("approval_requests")
    op.drop_table("writeback_configs")
    op.drop_table("shipments")
    op.drop_table("orders")


def downgrade() -> None:
    # Orders
    op.create_table(
        "orders",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("external_order_id", sa.Text(), nullable=True),
        sa.Column("order_status", sa.String(32), nullable=True),
        sa.Column("fulfillment_status", sa.String(32), nullable=True),
        sa.Column("total_amount", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("fulfilled_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_orders_tenant_id"), "orders", ["tenant_id"])
    op.create_index(op.f("ix_orders_customer_id"), "orders", ["customer_id"])

    # Shipments
    op.create_table(
        "shipments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("carrier", sa.Text(), nullable=True),
        sa.Column("tracking_number", sa.Text(), nullable=True),
        sa.Column("shipment_state", sa.String(32), nullable=True),
        sa.Column("shipment_confidence", sa.String(16), nullable=True),
        sa.Column("last_tracking_update", sa.DateTime(), nullable=True),
        sa.Column("estimated_delivery", sa.DateTime(), nullable=True),
        sa.Column("actual_delivery", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_shipments_tenant_id"), "shipments", ["tenant_id"])
    op.create_index(op.f("ix_shipments_customer_id"), "shipments", ["customer_id"])
    op.create_index(op.f("ix_shipments_order_id"), "shipments", ["order_id"])

    # writeback_configs
    op.create_table(
        "writeback_configs",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(32), nullable=False, server_default="off"),
        sa.Column("hubspot_note_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("hubspot_task_on_escalation", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("webhook_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id"),
    )

    # approval_requests
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("workflow_id", sa.UUID(), nullable=True),
        sa.Column("customer_id", sa.UUID(), nullable=True),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("action_value", postgresql.JSONB(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("expected_outcome", sa.Text(), nullable=True),
        sa.Column("risk_level", sa.String(16), nullable=True, server_default="medium"),
        sa.Column("ai_confidence", sa.Integer(), nullable=True, server_default=sa.text("0")),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("policy_reference", sa.Text(), nullable=True),
        sa.Column("simulation_result", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_approval_requests_tenant_id"), "approval_requests", ["tenant_id"])
