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
from sqlalchemy.dialects.postgresql import JSONB, UUID

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
    email_verified = Column(Boolean, default=True, nullable=False)
    trial_ends = Column(DateTime, default=lambda: datetime.utcnow() + timedelta(days=14))
    is_active = Column(Boolean, default=True, nullable=False)
    dialogs_used = Column(Integer, default=0, nullable=False)  # for billing FR-8
    resolved_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class CRMConfig(Base):
    __tablename__ = "crm_config"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True)
    provider = Column(String(32), default="custom_rest", nullable=False)
    read_url = Column(Text)
    write_url = Column(Text)
    headers = Column(JSONB, default=dict)
    read_mapping = Column(JSONB, default=dict)
    write_mapping = Column(JSONB, default=dict)
    capabilities = Column(JSONB, default=dict)
    # Integrations upgrade: controls which field is used as the customer lookup key
    primary_identifier = Column(String(32), default="email", nullable=False)


class CRMActionLog(Base):
    __tablename__ = "crm_action_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), index=True, nullable=False)
    user_id = Column(Text, index=True, nullable=False)
    action = Column(Text, nullable=False)
    status = Column(String(16), nullable=False)
    request = Column(JSONB, default=dict)
    response = Column(JSONB)
    error = Column(Text)
    latency_ms = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class CRMConnection(Base):
    __tablename__ = "crm_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), index=True, nullable=False)
    provider = Column(String(32), nullable=False, index=True)
    status = Column(String(16), default="connected", nullable=False)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    account_id = Column(Text)
    scopes = Column(JSONB, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ProactiveMetric(Base):
    __tablename__ = "proactive_metric"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True)
    metric_url = Column(Text)
    threshold = Column(Integer, default=30)  # % drop
    last_triggered_per_user = Column(JSONB, default=dict)


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


class AgentTool(Base):
    """Tenant-configured tools the agent can call (lookups and actions)."""
    __tablename__ = "agent_tools"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(64), nullable=False)          # unique per tenant, used as function name for LLM
    description = Column(Text, nullable=False)          # natural language — what it does, when to call it
    tool_type = Column(String(16), nullable=False)      # lookup | action
    method = Column(String(8), default="GET", nullable=False)   # GET | POST | PATCH | DELETE
    url_template = Column(Text, nullable=False)         # https://api.example.com/orders/{user_id}
    headers = Column(JSONB, default=dict)
    body_template = Column(JSONB, default=dict)         # static body merged with dynamic params
    # Parameters the LLM may fill in (OpenAI function params schema, JSONB)
    parameters = Column(JSONB, default=dict)
    require_confirmation = Column(Boolean, default=False, nullable=False)  # actions only
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AgentToolLog(Base):
    """Execution log for every agent tool call."""
    __tablename__ = "agent_tool_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), index=True, nullable=False)
    tool_id = Column(UUID(as_uuid=True), ForeignKey("agent_tools.id", ondelete="SET NULL"), nullable=True)
    tool_name = Column(String(64), nullable=False)
    user_id = Column(Text, index=True, nullable=False)
    status = Column(String(16), nullable=False)         # ok | failed | skipped
    request = Column(JSONB, default=dict)
    response = Column(JSONB)
    error = Column(Text)
    latency_ms = Column(Integer)
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


class NativeConnector(Base):
    """Stores credentials and status for native third-party integrations (Shopify, WooCommerce, Stripe)."""
    __tablename__ = "native_connectors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(32), nullable=False)           # shopify | woocommerce | stripe
    status = Column(String(16), default="connected", nullable=False)
    # Fernet-encrypted JSON blob containing provider-specific credentials
    credentials = Column(Text, nullable=False)
    meta = Column(JSONB, default=dict)                      # shop domain, account id, etc.
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", name="uq_native_connectors_tenant_provider"),
    )


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
