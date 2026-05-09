"""v2_workflow_tables

Revision ID: 2a3b4c5d6e7f
Revises: 426fa6a23c65
Create Date: 2026-05-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2a3b4c5d6e7f'
down_revision: Union[str, Sequence[str], None] = '426fa6a23c65'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — create v2 workflow tables."""

    # ── customers ──────────────────────────────────────────────
    op.create_table(
        'customers',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('email', sa.Text()),
        sa.Column('phone', sa.Text()),
        sa.Column('shopify_customer_id', sa.Text()),
        sa.Column('stripe_customer_id', sa.Text()),
        sa.Column('recharge_customer_id', sa.Text()),
        sa.Column('first_seen_at', sa.DateTime()),
        sa.Column('last_seen_at', sa.DateTime()),
        sa.Column('risk_level', sa.String(32)),
        sa.Column('sentiment_state', sa.String(32)),
        sa.Column('frustration_score', sa.Integer()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_customers_tenant_id', 'customers', ['tenant_id'])
    op.create_index('ix_customers_email', 'customers', ['email'])
    op.create_index('ix_customers_shopify_id', 'customers', ['shopify_customer_id'])
    op.create_index('ix_customers_stripe_id', 'customers', ['stripe_customer_id'])
    op.create_index('ix_customers_recharge_id', 'customers', ['recharge_customer_id'])

    # ── subscriptions ──────────────────────────────────────────
    op.create_table(
        'subscriptions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('customer_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('customers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('external_subscription_id', sa.Text()),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('plan_name', sa.Text()),
        sa.Column('product_sku', sa.Text()),
        sa.Column('renewal_date', sa.DateTime()),
        sa.Column('started_at', sa.DateTime()),
        sa.Column('pause_state', sa.String(32)),
        sa.Column('skip_state', sa.String(32)),
        sa.Column('mrr', sa.Integer()),
        sa.Column('currency', sa.String(8)),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_subscriptions_tenant_id', 'subscriptions', ['tenant_id'])
    op.create_index('ix_subscriptions_customer_id', 'subscriptions', ['customer_id'])
    op.create_index('ix_subscriptions_external_id', 'subscriptions', ['external_subscription_id'])
    op.create_index('ix_subscriptions_status', 'subscriptions', ['status'])

    # ── invoices ───────────────────────────────────────────────
    op.create_table(
        'invoices',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('customer_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('customers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('subscription_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('subscriptions.id', ondelete='SET NULL'), nullable=True),
        sa.Column('external_invoice_id', sa.Text()),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('amount_due', sa.Integer()),
        sa.Column('currency', sa.String(8)),
        sa.Column('payment_attempt_count', sa.Integer(), server_default='0'),
        sa.Column('last_failure_reason', sa.Text()),
        sa.Column('due_date', sa.DateTime()),
        sa.Column('paid_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_invoices_tenant_id', 'invoices', ['tenant_id'])
    op.create_index('ix_invoices_customer_id', 'invoices', ['customer_id'])
    op.create_index('ix_invoices_subscription_id', 'invoices', ['subscription_id'])
    op.create_index('ix_invoices_status', 'invoices', ['status'])

    # ── orders ─────────────────────────────────────────────────
    op.create_table(
        'orders',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('customer_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('customers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('external_order_id', sa.Text()),
        sa.Column('order_status', sa.String(32)),
        sa.Column('fulfillment_status', sa.String(32)),
        sa.Column('total_amount', sa.Integer()),
        sa.Column('currency', sa.String(8)),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('fulfilled_at', sa.DateTime()),
    )
    op.create_index('ix_orders_tenant_id', 'orders', ['tenant_id'])
    op.create_index('ix_orders_customer_id', 'orders', ['customer_id'])
    op.create_index('ix_orders_external_id', 'orders', ['external_order_id'])

    # ── shipments ──────────────────────────────────────────────
    op.create_table(
        'shipments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('customer_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('customers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('carrier', sa.Text()),
        sa.Column('tracking_number', sa.Text()),
        sa.Column('shipment_state', sa.String(32)),
        sa.Column('shipment_confidence', sa.String(16)),
        sa.Column('last_tracking_update', sa.DateTime()),
        sa.Column('estimated_delivery', sa.DateTime()),
        sa.Column('actual_delivery', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_shipments_order_id', 'shipments', ['order_id'])
    op.create_index('ix_shipments_customer_id', 'shipments', ['customer_id'])
    op.create_index('ix_shipments_tenant_id', 'shipments', ['tenant_id'])
    op.create_index('ix_shipments_tracking', 'shipments', ['tracking_number'])

    # ── workflows ──────────────────────────────────────────────
    op.create_table(
        'workflows',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('customer_id', sa.Text(), nullable=False),
        sa.Column('workflow_type', sa.String(64), nullable=False),
        sa.Column('current_state', sa.String(64), nullable=False),
        sa.Column('status', sa.String(32), nullable=False, server_default='active'),
        sa.Column('started_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime()),
        sa.Column('priority', sa.Integer(), server_default='0'),
        sa.Column('expiration_at', sa.DateTime()),
        sa.Column('locked_until', sa.DateTime()),
        sa.Column('escalation_state', sa.String(32)),
    )
    op.create_index('ix_workflows_tenant_id', 'workflows', ['tenant_id'])
    op.create_index('ix_workflows_customer_id', 'workflows', ['customer_id'])
    op.create_index('ix_workflows_type', 'workflows', ['workflow_type'])
    op.create_index('ix_workflows_status', 'workflows', ['status'])
    op.create_index('ix_workflows_active_lookup', 'workflows', ['tenant_id', 'workflow_type', 'status'])

    # ── workflow_transitions ───────────────────────────────────
    op.create_table(
        'workflow_transitions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('workflow_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('workflows.id', ondelete='CASCADE'), nullable=False),
        sa.Column('from_state', sa.String(64), nullable=False),
        sa.Column('to_state', sa.String(64), nullable=False),
        sa.Column('trigger_event', sa.Text()),
        sa.Column('decision_reason', sa.Text()),
        sa.Column('performed_by', sa.Text()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_workflow_transitions_workflow_id', 'workflow_transitions', ['workflow_id'])
    op.create_index('ix_workflow_transitions_created', 'workflow_transitions', ['created_at'])

    # ── canonical_events ───────────────────────────────────────
    op.create_table(
        'canonical_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.String(64), nullable=False),
        sa.Column('event_source', sa.String(64)),
        sa.Column('entity_type', sa.String(64)),
        sa.Column('entity_id', sa.Text()),
        sa.Column('payload', postgresql.JSONB(), server_default='{}'),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_canonical_events_tenant_id', 'canonical_events', ['tenant_id'])
    op.create_index('ix_canonical_events_type', 'canonical_events', ['event_type'])
    op.create_index('ix_canonical_events_entity', 'canonical_events', ['entity_type', 'entity_id'])

    # ── communications ─────────────────────────────────────────
    op.create_table(
        'communications',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('workflow_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('workflows.id', ondelete='CASCADE'), nullable=False),
        sa.Column('customer_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('customers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('channel', sa.String(32)),
        sa.Column('direction', sa.String(16)),
        sa.Column('message_type', sa.String(64)),
        sa.Column('delivery_status', sa.String(32)),
        sa.Column('deduplication_key', sa.Text()),
        sa.Column('sent_at', sa.DateTime()),
        sa.Column('delivered_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_communications_workflow_id', 'communications', ['workflow_id'])
    op.create_index('ix_communications_customer_id', 'communications', ['customer_id'])
    op.create_index('ix_communications_tenant_id', 'communications', ['tenant_id'])
    op.create_index('ix_communications_dedup', 'communications', ['deduplication_key'], unique=True, postgresql_nulls_not_distinct=True)

    # Note: postgresql_nulls_not_distinct requires PG15+. If on older PG, this will be a normal unique index.
    # If your PG < 15, either upgrade or remove this index and rely on app-level dedup.

    # ── escalations ────────────────────────────────────────────
    op.create_table(
        'escalations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('workflow_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('workflows.id', ondelete='CASCADE'), nullable=False),
        sa.Column('customer_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('customers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('escalation_reason', sa.Text()),
        sa.Column('severity', sa.String(16)),
        sa.Column('owner_id', sa.Text()),
        sa.Column('status', sa.String(32), nullable=False, server_default='open'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('resolved_at', sa.DateTime()),
    )
    op.create_index('ix_escalations_workflow_id', 'escalations', ['workflow_id'])
    op.create_index('ix_escalations_tenant_id', 'escalations', ['tenant_id'])
    op.create_index('ix_escalations_status', 'escalations', ['status'])

    # ── timeline_events ────────────────────────────────────────
    op.create_table(
        'timeline_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('entity_type', sa.String(64)),
        sa.Column('entity_id', sa.Text()),
        sa.Column('event_type', sa.String(64), nullable=False),
        sa.Column('event_source', sa.String(64)),
        sa.Column('payload', postgresql.JSONB(), server_default='{}'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_timeline_events_tenant_id', 'timeline_events', ['tenant_id'])
    op.create_index('ix_timeline_events_entity', 'timeline_events', ['entity_type', 'entity_id'])
    op.create_index('ix_timeline_events_type', 'timeline_events', ['event_type'])

    # ── ai_interactions ────────────────────────────────────────
    op.create_table(
        'ai_interactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('workflow_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('workflows.id', ondelete='CASCADE'), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('interaction_type', sa.String(64)),
        sa.Column('input_context', postgresql.JSONB(), server_default='{}'),
        sa.Column('output', sa.Text()),
        sa.Column('confidence', sa.Integer()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_ai_interactions_workflow_id', 'ai_interactions', ['workflow_id'])
    op.create_index('ix_ai_interactions_tenant_id', 'ai_interactions', ['tenant_id'])
    op.create_index('ix_ai_interactions_type', 'ai_interactions', ['interaction_type'])

    # ── policy_sets ────────────────────────────────────────────
    op.create_table(
        'policy_sets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('retry_policy', postgresql.JSONB(), server_default='{}'),
        sa.Column('communication_policy', postgresql.JSONB(), server_default='{}'),
        sa.Column('escalation_policy', postgresql.JSONB(), server_default='{}'),
        sa.Column('approval_policy', postgresql.JSONB(), server_default='{}'),
        sa.Column('enabled_workflows', postgresql.JSONB(), server_default='[]'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_policy_sets_tenant_id', 'policy_sets', ['tenant_id'])


def downgrade() -> None:
    """Downgrade schema — drop all v2 workflow tables."""
    op.drop_table('policy_sets')
    op.drop_table('ai_interactions')
    op.drop_table('timeline_events')
    op.drop_table('escalations')
    op.drop_table('communications')
    op.drop_table('canonical_events')
    op.drop_table('workflow_transitions')
    op.drop_table('workflows')
    op.drop_table('shipments')
    op.drop_table('orders')
    op.drop_table('invoices')
    op.drop_table('subscriptions')
    op.drop_table('customers')
