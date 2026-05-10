"""ORM models matching the spec (5.5 Data schemas)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import UUID
JSONB = JSON  # Use JSON for dev (SQLite), JSONB in production (PostgreSQL)

from .db import Base


def _uuid():
    return uuid.uuid4()


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name = Column(Text, nullable=False)
    email = Column(Text, unique=True, nullable=False, index=True)
    hashed_password = Column(Text, nullable=False)
    # DEFAULT: email auto-verified in MVP; verification_token stored but link only logged.
    email_verified = Column(Boolean, default=False, nullable=False)
    trial_ends = Column(DateTime, default=lambda: datetime.utcnow() + timedelta(days=14))
    is_active = Column(Boolean, default=True, nullable=False)
    dialogs_used = Column(Integer, default=0, nullable=False)  # for billing FR-8
    resolved_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class FileRecord(Base):
    __tablename__ = "files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(Text, nullable=False)
    s3_key = Column(Text)  # used as local path in MVP
    status = Column(String(32), default="processing", nullable=False)  # processing/ready/failed
    # Sprint 1: dedup + observability
    content_hash = Column(String(64), index=True)  # SHA-256 of the file bytes
    chunks_total = Column(Integer, default=0, nullable=False)
    size_bytes = Column(Integer, default=0, nullable=False)
    error = Column(Text)  # populated when status=failed
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ChatLog(Base):
    __tablename__ = "chat_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), index=True, nullable=False)
    user_id = Column(Text, index=True, nullable=False)
    direction = Column(String(16), nullable=False)  # incoming/outgoing
    message = Column(Text)
    response = Column(Text)
    resolution = Column(String(16))  # resolved/escalated
    action_called = Column(Text)
    latency_ms = Column(Integer)
    delivered = Column(Boolean, default=False, nullable=False)  # for outgoing proactive -> widget inbox
    # Sprint 1: explainability — retrieval trace used for this turn.
    # Shape: [{source_id:"S1", file_id, filename, section, page, score, snippet}, ...]
    sources = Column(JSONB)
    # Integrations upgrade: session grouping and arbitrary extra fields from widget.identify()
    session_id = Column(UUID(as_uuid=True), index=True, nullable=True)
    extra_fields = Column(JSONB, default=dict)
    channel = Column(String(32), default="web_widget", nullable=False)  # web_widget, telegram, whatsapp
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ConversationRating(Base):
    """User rating for a conversation. Tied to the last outgoing (bot response) message."""
    __tablename__ = "conversation_ratings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Text, index=True, nullable=False)
    message_id = Column(UUID(as_uuid=True), nullable=True)  # the last outgoing message in the conversation
    rating = Column(String(16), nullable=False)  # thumbs_up / thumbs_down
    feedback = Column(Text, default="")            # optional text feedback
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class WebhookConfig(Base):
    """Per-tenant webhook configuration for incoming context and outgoing event notifications."""
    __tablename__ = "webhook_configs"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True)
    incoming_url = Column(Text)
    incoming_secret = Column(Text)                          # Fernet-encrypted HMAC secret
    outgoing_url = Column(Text)
    outgoing_secret = Column(Text)                          # Fernet-encrypted HMAC secret
    field_mapping = Column(JSONB, default=dict)             # maps incoming response keys → agent context keys
    events = Column(JSONB, default=list)                    # list of event names to fire outgoing webhook for
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class WriteBackConfig(Base):
    """Per-tenant configuration for writing conversation summaries back to CRM or webhook."""
    __tablename__ = "writeback_configs"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True)
    type = Column(String(32), default="off", nullable=False)            # off | hubspot_note | webhook
    hubspot_note_enabled = Column(Boolean, default=False, nullable=False)
    hubspot_task_on_escalation = Column(Boolean, default=False, nullable=False)
    webhook_url = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ChannelConfig(Base):
    """Per-tenant channel configuration for omnichannel support (widget, telegram, whatsapp, etc)."""
    __tablename__ = "channels_config"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_type = Column(String(32), nullable=False)  # web_widget, telegram, whatsapp, email, instagram
    config = Column(JSONB, default=dict)              # channel-specific credentials and settings
    status = Column(String(16), default="inactive", nullable=False)  # active, inactive, error
    last_error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "channel_type", name="uq_channels_config_tenant_type"),
    )


class ApiKey(Base):
    """Tenant API keys for server-to-server REST integrations."""
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(128), nullable=False)          # human-readable label (e.g. "Production", "Staging")
    key_hash = Column(String(64), unique=True, nullable=False, index=True)  # SHA-256 of the raw key
    prefix = Column(String(8), nullable=False)          # first 8 chars for identification (sk_abc12345...)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)        # NULL = never expires


# ═══════════════════════════════════════════════════════════════
# v2 Workflow Domain Models
# ═══════════════════════════════════════════════════════════════


class Customer(Base):
    """Canonical cross-system customer identity."""
    __tablename__ = "customers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    email = Column(Text)
    phone = Column(Text)
    shopify_customer_id = Column(Text)
    stripe_customer_id = Column(Text)
    recharge_customer_id = Column(Text)
    first_seen_at = Column(DateTime)
    last_seen_at = Column(DateTime)
    risk_level = Column(String(32))
    sentiment_state = Column(String(32))
    frustration_score = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Subscription(Base):
    """Canonical subscription state (source of truth: Recharge)."""
    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    external_subscription_id = Column(Text)
    status = Column(String(32), nullable=False)
    plan_name = Column(Text)
    product_sku = Column(Text)
    renewal_date = Column(DateTime)
    started_at = Column(DateTime)
    pause_state = Column(String(32))
    skip_state = Column(String(32))
    mrr = Column(Integer)
    currency = Column(String(8))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Invoice(Base):
    """Canonical billing/payment entity (source of truth: Stripe)."""
    __tablename__ = "invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True)
    external_invoice_id = Column(Text)
    status = Column(String(32), nullable=False)
    amount_due = Column(Integer)
    currency = Column(String(8))
    payment_attempt_count = Column(Integer, default=0)
    last_failure_reason = Column(Text)
    due_date = Column(DateTime)
    paid_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PaymentFailure(Base):
    """Operational payment failure object tracked across retry lifecycle."""
    __tablename__ = "payment_failures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    failure_type = Column(Text)
    failure_category = Column(Text)
    recoverability = Column(String(32))
    attempt_number = Column(Integer, default=0)
    detected_at = Column(DateTime, nullable=False)
    last_retry_at = Column(DateTime)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Order(Base):
    """Canonical commerce order (source of truth: Shopify)."""
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    external_order_id = Column(Text)
    order_status = Column(String(32))
    fulfillment_status = Column(String(32))
    total_amount = Column(Integer)
    currency = Column(String(8))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    fulfilled_at = Column(DateTime)


class Shipment(Base):
    """Canonical shipment object with carrier lifecycle."""
    __tablename__ = "shipments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    carrier = Column(Text)
    tracking_number = Column(Text)
    shipment_state = Column(String(32))
    shipment_confidence = Column(String(16))
    last_tracking_update = Column(DateTime)
    estimated_delivery = Column(DateTime)
    actual_delivery = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Workflow(Base):
    """Canonical operational workflow instance."""
    __tablename__ = "workflows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = Column(Text, nullable=False)
    workflow_type = Column(String(64), nullable=False)
    current_state = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="active")
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime)
    priority = Column(Integer, default=0)
    expiration_at = Column(DateTime)
    locked_until = Column(DateTime)
    escalation_state = Column(String(32))


class WorkflowTransition(Base):
    """Explicit workflow state transition history."""
    __tablename__ = "workflow_transitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True)
    from_state = Column(String(64), nullable=False)
    to_state = Column(String(64), nullable=False)
    trigger_event = Column(Text)
    decision_reason = Column(Text)
    policy_snapshot = Column(JSONB, default=dict)
    performed_by = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class CanonicalEvent(Base):
    """Ingested canonical event from external sources."""
    __tablename__ = "canonical_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    event_source = Column(String(64))
    entity_type = Column(String(64))
    entity_id = Column(Text)
    payload = Column(JSONB, default=dict)
    occurred_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Communication(Base):
    """Canonical customer communication as workflow artifact."""
    __tablename__ = "communications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    channel = Column(String(32))
    direction = Column(String(16))
    message_type = Column(String(64))
    template_name = Column(String(64))
    delivery_status = Column(String(32))
    deduplication_key = Column(Text)
    sent_at = Column(DateTime)
    delivered_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Escalation(Base):
    """Human intervention / escalation object."""
    __tablename__ = "escalations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    escalation_reason = Column(Text)
    severity = Column(String(16))
    owner_id = Column(Text)
    assigned_to = Column(Text)
    source = Column(String(64))
    extra_metadata = Column(JSONB, default=dict)
    sla_breached = Column(Boolean, default=False)
    status = Column(String(32), nullable=False, default="OPEN")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class TimelineEvent(Base):
    """Unified operational audit / timeline event."""
    __tablename__ = "timeline_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    entity_type = Column(String(64))
    entity_id = Column(Text)
    event_type = Column(String(64), nullable=False, index=True)
    event_source = Column(String(64))
    payload = Column(JSONB, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AIInteraction(Base):
    """Bounded AI reasoning artifact (classification, generation)."""
    __tablename__ = "ai_interactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    interaction_type = Column(String(64))
    input_context = Column(JSONB, default=dict)
    output = Column(Text)
    confidence = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PolicySet(Base):
    """Merchant operational governance policies."""
    __tablename__ = "policy_sets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    retry_policy = Column(JSONB, default=dict)
    communication_policy = Column(JSONB, default=dict)
    escalation_policy = Column(JSONB, default=dict)
    approval_policy = Column(JSONB, default=dict)
    enabled_workflows = Column(JSONB, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class NativeConnector(Base):
    """Third-party connector credentials (Shopify, Stripe, etc.)."""
    __tablename__ = "native_connectors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(32), nullable=False)
    status = Column(String(16), nullable=False, default="connected")
    credentials = Column(Text, nullable=False)
    meta = Column(JSONB, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ApprovalRequest(Base):
    """Approval request requiring human review before bounded AI action."""
    __tablename__ = "approval_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True)
    action_type = Column(String(64), nullable=False)
    action_value = Column(JSONB, default=dict)
    reason = Column(Text)
    expected_outcome = Column(Text)
    risk_level = Column(String(16), default="medium")
    ai_confidence = Column(Integer, default=0)
    status = Column(String(32), nullable=False, default="PENDING")
    reviewed_by = Column(Text)
    reviewed_at = Column(DateTime)
    policy_reference = Column(Text)
    simulation_result = Column(JSONB, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class NotificationPreferences(Base):
    """Per-tenant notification settings."""
    __tablename__ = "notification_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    escalation_alerts = Column(Boolean, default=True)
    approval_alerts = Column(Boolean, default=True)
    workflow_failure_alerts = Column(Boolean, default=True)
    daily_summary = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
