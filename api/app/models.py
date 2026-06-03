"""ORM models matching the spec (5.5 Data schemas)."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timedelta

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import UUID

from .db import Base

JSONB = JSON  # Use JSON for dev (SQLite), JSONB in production (PostgreSQL)


def _uuid():
    return uuid.uuid4()


class _UUIDMixin:
    """UUID primary key."""
    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)


class _TenantFK:
    """Foreign key to tenants table — for tenant-scoped models."""
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)


class _TenantScoped(_UUIDMixin, _TenantFK):
    """UUID PK + tenant FK — most tenant-scoped models."""


class _CreatedAt:
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class _UpdatedAt:
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Tenant(Base, _UUIDMixin, _CreatedAt):
    __tablename__ = "tenants"

    name = Column(Text, nullable=False)
    email = Column(Text, unique=True, nullable=False, index=True)
    hashed_password = Column(Text, nullable=False)
    # DEFAULT: email auto-verified in MVP; verification_token stored but link only logged.
    email_verified = Column(Boolean, default=False, nullable=False)
    trial_ends = Column(DateTime, default=lambda: datetime.utcnow() + timedelta(days=14))
    is_active = Column(Boolean, default=True, nullable=False)
    dialogs_used = Column(Integer, default=0, nullable=False)  # for billing FR-8
    resolved_count = Column(Integer, default=0, nullable=False)
    # CRM integration config (provider-agnostic)
    crm_provider = Column(String(50), default="pabau", nullable=False)
    crm_config = Column(JSONB, default=dict)
    agent_config = Column(JSONB, default=dict)
    # id + created_at inherited from mixins


class FileRecord(Base, _TenantScoped, _CreatedAt):
    __tablename__ = "files"
    filename = Column(Text, nullable=False)
    s3_key = Column(Text)  # used as local path in MVP
    status = Column(String(32), default="processing", nullable=False)  # processing/ready/failed
    # Sprint 1: dedup + observability
    content_hash = Column(String(64), index=True)  # SHA-256 of the file bytes
    chunks_total = Column(Integer, default=0, nullable=False)
    size_bytes = Column(Integer, default=0, nullable=False)
    error = Column(Text)  # populated when status=failed
    file_type = Column(String(32), default="document", nullable=False)  # document, catalog, compatibility
    metadata_schema = Column(JSONB)  # CSV column mapping for structured imports
    folder_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_folders.id", ondelete="SET NULL"), nullable=True, index=True)
    # created_at inherited from _CreatedAt


class KnowledgeFolder(Base, _TenantScoped, _CreatedAt, _UpdatedAt):
    """Hierarchical folder structure for organizing knowledge base files."""
    __tablename__ = "knowledge_folders"

    name = Column(Text, nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_folders.id", ondelete="CASCADE"), nullable=True, index=True)
    sort_order = Column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", "parent_id", name="uq_knowledge_folder_name_per_parent"),
    )


class KnowledgeUrl(Base, _TenantScoped, _CreatedAt):
    """Imported URL for knowledge base web scraping."""
    __tablename__ = "knowledge_urls"

    url = Column(Text, nullable=False)
    title = Column(Text)
    status = Column(String(16), default="pending", nullable=False)  # pending | processing | ready | failed
    folder_id = Column(UUID(as_uuid=True), ForeignKey("knowledge_folders.id", ondelete="SET NULL"), nullable=True, index=True)
    chunks_total = Column(Integer, default=0)
    error = Column(Text)


# Phase 1: ProductCatalog, CatalogVariant, Compatibility removed — e-commerce concepts


class ChatLog(Base, _TenantScoped, _CreatedAt):
    __tablename__ = "chat_logs"

    # id, tenant_id inherited from _TenantScoped
    user_id = Column(Text, index=True, nullable=False)
    direction = Column(String(16), nullable=False)  # incoming/outgoing
    message = Column(Text)
    response = Column(Text)
    resolution = Column(String(16))  # resolved/escalated
    action_called = Column(Text)
    latency_ms = Column(Integer)
    delivered = Column(Boolean, default=False, nullable=False)
    sources = Column(JSONB)
    session_id = Column(UUID(as_uuid=True), index=True, nullable=True)
    extra_fields = Column(JSONB, default=dict)
    channel = Column(String(32), default="web_widget", nullable=False)
    # created_at inherited from _CreatedAt


class ConversationRating(Base, _TenantScoped, _CreatedAt):
    """User rating for a conversation. Tied to the last outgoing (bot response) message."""
    __tablename__ = "conversation_ratings"

    user_id = Column(Text, index=True, nullable=False)
    message_id = Column(UUID(as_uuid=True), nullable=True)  # the last outgoing message in the conversation
    rating = Column(String(16), nullable=False)  # thumbs_up / thumbs_down
    feedback = Column(Text, default="")            # optional text feedback


class WebhookConfig(Base, _CreatedAt, _UpdatedAt):
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




class ChannelConfig(Base, _TenantScoped, _CreatedAt, _UpdatedAt):
    """Per-tenant channel configuration for omnichannel support (widget, telegram, whatsapp, etc)."""
    __tablename__ = "channels_config"

    channel_type = Column(String(32), nullable=False)      # web_widget, whatsapp, instagram
    config = Column(JSONB, default=dict)              # channel-specific credentials and settings
    status = Column(String(16), default="inactive", nullable=False)  # active, inactive, error
    last_error = Column(Text)

    __table_args__ = (
        UniqueConstraint("tenant_id", "channel_type", name="uq_channels_config_tenant_type"),
    )


class ApiKey(Base, _TenantScoped, _CreatedAt):
    """Tenant API keys for server-to-server REST integrations."""
    __tablename__ = "api_keys"

    name = Column(String(128), nullable=False)          # human-readable label (e.g. "Production", "Staging")
    key_hash = Column(String(64), unique=True, nullable=False, index=True)  # SHA-256 of the raw key
    prefix = Column(String(8), nullable=False)          # first 8 chars for identification (sk_abc12345...)
    last_used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)        # NULL = never expires


# ═══════════════════════════════════════════════════════════════
# Inbox / Operations Center Models
# ═══════════════════════════════════════════════════════════════


class ConversationState(str, enum.Enum):
    ACTIVE = "active"
    WAITING = "waiting"
    HANDOFF_REQUESTED = "handoff_requested"
    ASSIGNED = "assigned"
    CLOSED = "closed"


class Conversation(Base, _TenantScoped, _CreatedAt, _UpdatedAt):
    """A customer conversation — the core inbox entity."""
    __tablename__ = "conversations"

    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True, index=True)
    user_id = Column(Text, nullable=False, index=True)
    user_display_name = Column(Text, nullable=True)
    channel = Column(String(32), nullable=False, default="web_widget")

    status = Column(String(32), nullable=False, default=ConversationState.ACTIVE.value, index=True)
    assigned_to = Column(Text, nullable=True)
    assigned_at = Column(DateTime, nullable=True)

    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_message_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    closed_at = Column(DateTime, nullable=True)

    last_message_preview = Column(Text, nullable=True)
    message_count = Column(Integer, default=0, nullable=False)
    unread_count = Column(Integer, default=0, nullable=False)

    workflow_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    workflow_type = Column(String(64), nullable=True)
    workflow_state = Column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_conversations_tenant_status", "tenant_id", "status"),
        Index("ix_conversations_tenant_user", "tenant_id", "user_id"),
    )


class MessageDirection(str, enum.Enum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"
    NOTE = "note"


class Message(Base, _TenantScoped, _CreatedAt):
    """A single message in a conversation."""
    __tablename__ = "messages"

    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False, index=True)

    direction = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    content_type = Column(String(32), default="text")

    sender_type = Column(String(16), nullable=False, default="customer")
    operator_id = Column(Text, nullable=True)

    sources = Column(JSONB, nullable=True)
    confidence = Column(Float, nullable=True)

    delivered = Column(Boolean, default=False)
    read_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )


class OperatorNote(Base, _TenantScoped, _CreatedAt):
    """Internal operator notes attached to conversations."""
    __tablename__ = "operator_notes"

    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    operator_id = Column(Text, nullable=False)


class CannedResponse(Base, _TenantScoped, _CreatedAt, _UpdatedAt):
    """Saved reply templates for operator use."""
    __tablename__ = "canned_responses"

    title = Column(String(128), nullable=False)
    content = Column(Text, nullable=False)
    shortcut = Column(String(32), nullable=True)
    category = Column(String(64), nullable=True)


# ═══════════════════════════════════════════════════════════════
# v2 Workflow Domain Models
# ═══════════════════════════════════════════════════════════════


class Customer(Base, _TenantScoped, _CreatedAt, _UpdatedAt):
    """Canonical cross-system customer/patient identity."""
    __tablename__ = "customers"

    email = Column(Text)
    phone = Column(Text)

    # Profile
    display_name = Column(Text, nullable=True)
    avatar_url = Column(Text, nullable=True)
    locale = Column(String(16), nullable=True)
    timezone = Column(String(64), nullable=True)
    tags = Column(JSONB, nullable=True, default=list)

    # Activity
    total_conversations = Column(Integer, default=0)
    total_workflows = Column(Integer, default=0)
    first_seen_at = Column(DateTime)
    last_seen_at = Column(DateTime)
    last_message_at = Column(DateTime, nullable=True)


# Phase 1: Subscription, Invoice, PaymentFailure removed — e-commerce concepts




class Workflow(Base, _TenantScoped, _UpdatedAt):
    """Canonical operational workflow instance."""
    __tablename__ = "workflows"

    customer_id = Column(Text, nullable=False)
    order_id = Column(Text, nullable=True)
    workflow_type = Column(String(64), nullable=False)
    current_state = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="active")
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime)
    priority = Column(Integer, default=0)
    expiration_at = Column(DateTime)
    locked_until = Column(DateTime)
    escalation_state = Column(String(32))


class WorkflowTransition(Base, _UUIDMixin, _CreatedAt):
    """Explicit workflow state transition history."""
    __tablename__ = "workflow_transitions"

    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True)
    from_state = Column(String(64), nullable=False)
    to_state = Column(String(64), nullable=False)
    trigger_event = Column(Text)
    decision_reason = Column(Text)
    policy_snapshot = Column(JSONB, default=dict)
    performed_by = Column(Text)


class CanonicalEvent(Base, _UUIDMixin, _CreatedAt):
    """Ingested canonical event from external sources."""
    __tablename__ = "canonical_events"

    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # no FK — events may arrive before tenant exists
    event_type = Column(String(64), nullable=False, index=True)
    event_source = Column(String(64))
    entity_type = Column(String(64))
    entity_id = Column(Text)
    payload = Column(JSONB, default=dict)
    occurred_at = Column(DateTime, nullable=False)


class Communication(Base, _TenantScoped, _CreatedAt):
    """Canonical customer communication as workflow artifact."""
    __tablename__ = "communications"

    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    channel = Column(String(32))
    direction = Column(String(16))
    message_type = Column(String(64))
    template_name = Column(String(64))
    delivery_status = Column(String(32))
    deduplication_key = Column(Text)
    sent_at = Column(DateTime)
    delivered_at = Column(DateTime)


# Phase 1: Escalation model removed — will be rebuilt for medical in later phases


class TimelineEvent(Base, _UUIDMixin, _CreatedAt):
    """Unified operational audit / timeline event."""
    __tablename__ = "timeline_events"

    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)  # no FK — may reference deleted tenants
    entity_type = Column(String(64))
    entity_id = Column(Text)
    event_type = Column(String(64), nullable=False, index=True)
    event_source = Column(String(64))
    payload = Column(JSONB, default=dict)


class AIInteraction(Base, _TenantScoped, _CreatedAt):
    """Bounded AI reasoning artifact (classification, generation)."""
    __tablename__ = "ai_interactions"

    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True)
    interaction_type = Column(String(64))
    input_context = Column(JSONB, default=dict)
    output = Column(Text)
    confidence = Column(Integer)


# Phase 1: PolicySet model removed — will be rebuilt for medical in later phases


# Phase 1: NotificationPreferences model removed


class Patient(Base, _TenantScoped, _CreatedAt, _UpdatedAt):
    """Medical patient — canonical patient identity for clinic context."""
    __tablename__ = "patients"

    external_id = Column(Text)                              # CRM patient ID
    first_name = Column(Text, nullable=False)
    last_name = Column(Text, nullable=False)
    email = Column(Text)
    phone = Column(Text, nullable=False)
    date_of_birth = Column(DateTime)
    gender = Column(String(16))

    # Consent management
    consent_status = Column(String(16), default="pending")  # pending | granted | revoked | expired
    consent_timestamp = Column(DateTime)
    consent_channel = Column(String(32))                     # whatsapp | widget | web | admin
    gdpr_data_retention = Column(String(32))                 # retention policy applied

    extra_data = Column(JSONB, default=dict)                 # CRM-specific fields


class AppointmentCache(Base, _TenantScoped, _CreatedAt, _UpdatedAt):
    """Local cache for appointment operational state.
    Source of truth is always the external CRM.
    """
    __tablename__ = "appointment_cache"

    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True)
    external_id = Column(Text, nullable=False, index=True)  # CRM record ID

    # Operational state (NOT source of truth)
    status = Column(String(32), default="scheduled")         # cached for AI workflow
    slot_token = Column(String(64))                          # optimistic lock
    reminder_sent_24h = Column(Boolean, default=False)        # reminder state
    reminder_sent_2h = Column(Boolean, default=False)         # reminder state
    consent_id = Column(UUID(as_uuid=True), nullable=True)   # compliance ref
    source = Column(String(32), default="whatsapp")          # how it was created

    # Cache metadata
    cached_at = Column(DateTime, default=datetime.utcnow)
    last_synced_at = Column(DateTime, default=datetime.utcnow)


class ConsentLog(Base, _TenantScoped):
    """Immutable consent journal (GDPR Art. 7)."""
    __tablename__ = "consent_logs"

    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=True, index=True)
    type = Column(String(32), nullable=False)                # marketing | appointment | phi_whatsapp | data_processing
    status = Column(String(16), nullable=False, default="granted")  # granted | revoked | expired
    channel = Column(String(32), nullable=False)             # whatsapp | widget | web | admin
    consent_text = Column(Text, nullable=False)              # exact text patient agreed to
    ip_address = Column(String(45))
    user_agent = Column(Text)
    granted_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime)
    expires_at = Column(DateTime)

    __table_args__ = (
        Index("ix_consent_logs_tenant_type_status", "tenant_id", "type", "status"),
    )


class Provider(Base, _TenantScoped, _CreatedAt, _UpdatedAt):
    """Healthcare provider / doctor."""
    __tablename__ = "providers"

    external_id = Column(Text)                              # CRM provider ID
    name = Column(Text, nullable=False)
    specialty = Column(Text)
    email = Column(Text)
    phone = Column(Text)
    schedule = Column(JSONB, default=dict)                  # availability rules


class AuditLog(Base, _TenantScoped):
    """Extended compliance audit log (GDPR Art. 30 / HIPAA)."""
    __tablename__ = "audit_logs"

    patient_id = Column(UUID(as_uuid=True), ForeignKey("patients.id"), nullable=True)
    actor_type = Column(String(16), nullable=False)          # patient | staff | system | whatsapp
    actor_id = Column(Text)
    action = Column(String(64), nullable=False)               # message_sent | appointment_booked | consent_granted | phi_accessed | data_deleted
    resource_type = Column(String(32))
    resource_id = Column(Text)
    details = Column(JSONB, default=dict)                    # NOT raw PHI — references/tokens only
    ip_address = Column(String(45))
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    retention_until = Column(DateTime)

    __table_args__ = (
        Index("ix_audit_logs_tenant_action", "tenant_id", "action"),
        Index("ix_audit_logs_tenant_timestamp", "tenant_id", "timestamp"),
    )


class Campaign(Base, _TenantScoped, _CreatedAt, _UpdatedAt):
    """Marketing campaign."""
    __tablename__ = "campaigns"

    name = Column(Text, nullable=False)
    trigger_type = Column(String(32), nullable=False, default="manual")
    trigger_config = Column(JSONB, default=dict)
    message_template = Column(Text, default="")
    target_filters = Column(JSONB, default=dict)
    status = Column(String(16), nullable=False, default="draft")
    metrics = Column(JSONB, default=dict)
    start_at = Column(DateTime)
    end_at = Column(DateTime)


# ═══════════════════════════════════════════════════════════════
# Phase 6: Settings & Billing Models
# ═══════════════════════════════════════════════════════════════


class TeamMember(Base, _TenantScoped, _CreatedAt):
    """Company team member with role-based access."""
    __tablename__ = "team_members"

    email = Column(String(255), nullable=False)
    name = Column(String(255), nullable=True)
    role = Column(String(32), nullable=False, default="operator")  # owner | manager | operator
    invited_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_team_members_tenant_email"),
    )


class BillingPlan(Base, _UUIDMixin, _CreatedAt):
    """Pre-defined billing plan with resource limits."""
    __tablename__ = "billing_plans"

    name = Column(String(64), unique=True, nullable=False)  # free | starter | pro | enterprise
    price_usd = Column(Integer, default=0, nullable=False)
    resolved_limit = Column(Integer, default=10, nullable=False)
    storage_limit_mb = Column(Integer, default=500, nullable=False)
    agent_limit = Column(Integer, default=3, nullable=False)


class ActivityLog(Base, _TenantScoped, _CreatedAt):
    """Append-only AI activity log (black box)."""
    __tablename__ = "activity_logs"

    initiator = Column(String(255), nullable=False)
    event_type = Column(String(64), nullable=False)
    description = Column(Text, nullable=False, default="")
    patient_reference = Column(String(255), nullable=True)
    crm_id = Column(String(128), nullable=True)
    api_status = Column(String(32), nullable=False, default="success")  # success | error | pending
    extra_meta = Column(JSONB, nullable=True)
