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
    file_type = Column(String(32), default="document", nullable=False)  # document, catalog, compatibility
    metadata_schema = Column(JSONB)  # CSV column mapping for structured imports
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# Phase 1: ProductCatalog, CatalogVariant, Compatibility removed — e-commerce concepts


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
# Inbox / Operations Center Models
# ═══════════════════════════════════════════════════════════════


class ConversationState(str, enum.Enum):
    ACTIVE = "active"
    WAITING = "waiting"
    HANDOFF_REQUESTED = "handoff_requested"
    ASSIGNED = "assigned"
    CLOSED = "closed"


class Conversation(Base):
    """A customer conversation — the core inbox entity."""
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)

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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

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


class Message(Base):
    """A single message in a conversation."""
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
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

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )


class OperatorNote(Base):
    """Internal operator notes attached to conversations."""
    __tablename__ = "operator_notes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    operator_id = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class CannedResponse(Base):
    """Saved reply templates for operator use."""
    __tablename__ = "canned_responses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
    title = Column(String(128), nullable=False)
    content = Column(Text, nullable=False)
    shortcut = Column(String(32), nullable=True)
    category = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# ═══════════════════════════════════════════════════════════════
# v2 Workflow Domain Models
# ═══════════════════════════════════════════════════════════════


class Customer(Base):
    """Canonical cross-system customer/patient identity."""
    __tablename__ = "customers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
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

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# Phase 1: Subscription, Invoice, PaymentFailure removed — e-commerce concepts




class Workflow(Base):
    """Canonical operational workflow instance."""
    __tablename__ = "workflows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = Column(Text, nullable=False)
    order_id = Column(Text, nullable=True)
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


# Phase 1: Escalation model removed — will be rebuilt for medical in later phases


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


# Phase 1: PolicySet model removed — will be rebuilt for medical in later phases


class NativeConnector(Base):
    """Third-party connector credentials (CRM, etc.)."""
    __tablename__ = "native_connectors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(32), nullable=False)
    status = Column(String(16), nullable=False, default="connected")
    credentials = Column(Text, nullable=False)
    meta = Column(JSONB, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# Phase 1: NotificationPreferences model removed


class Patient(Base):
    """Medical patient — canonical patient identity for clinic context."""
    __tablename__ = "patients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AppointmentCache(Base):
    """Local cache for appointment operational state.
    Source of truth is always the external CRM.
    """
    __tablename__ = "appointment_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ConsentLog(Base):
    """Immutable consent journal (GDPR Art. 7)."""
    __tablename__ = "consent_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
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


class Provider(Base):
    """Healthcare provider / doctor."""
    __tablename__ = "providers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    external_id = Column(Text)                              # CRM provider ID
    name = Column(Text, nullable=False)
    specialty = Column(Text)
    email = Column(Text)
    phone = Column(Text)
    schedule = Column(JSONB, default=dict)                  # availability rules
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class CrmConnection(Base):
    """CRM provider connection config."""
    __tablename__ = "crm_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(32), nullable=False)             # zoho | hubspot | salesforce | custom_api
    config = Column(JSONB, default=dict)                     # encrypted credentials, endpoints, mappings
    status = Column(String(16), nullable=False, default="disconnected")  # connected | disconnected | error
    last_sync_at = Column(DateTime)
    webhook_secret = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class CalendarConnection(Base):
    """Calendar provider connection config (Google Calendar, Outlook, etc.)."""
    __tablename__ = "calendar_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(32), nullable=False)             # google | outlook
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text)
    token_expiry = Column(DateTime)
    calendar_id = Column(String(256))                         # default "primary" or specific calendar
    config = Column(JSONB, default=dict)                      # provider-specific settings
    status = Column(String(16), nullable=False, default="disconnected")  # connected | disconnected | error
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AuditLog(Base):
    """Extended compliance audit log (GDPR Art. 30 / HIPAA)."""
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
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


class Campaign(Base):
    """Marketing campaign."""
    __tablename__ = "campaigns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(Text, nullable=False)
    trigger_type = Column(String(32), nullable=False, default="manual")
    trigger_config = Column(JSONB, default=dict)
    message_template = Column(Text, default="")
    target_filters = Column(JSONB, default=dict)
    status = Column(String(16), nullable=False, default="draft")
    metrics = Column(JSONB, default=dict)
    start_at = Column(DateTime)
    end_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
