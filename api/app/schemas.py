"""Pydantic request/response schemas."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    tenant_name: str


class AuthOut(BaseModel):
    tenant_id: UUID
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class ChatIn(BaseModel):
    user_id: str = Field(min_length=1, max_length=256)
    message: str = Field(min_length=1, max_length=4000)
    channel: str = "rest_api"


class ChatOut(BaseModel):
    response: str
    action_called: str | None = None
    latency_ms: int


class WidgetChatIn(BaseModel):
    tenant_id: UUID
    user_id: str = Field(min_length=1, max_length=256)
    message: str = Field(min_length=1, max_length=4000)
    channel: str = "web_widget"
    extra_fields: dict[str, Any] = Field(default_factory=dict)


class CRMConfigIn(BaseModel):
    provider: str = "custom_rest"
    read_url: str | None = None
    write_url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    read_mapping: dict[str, str] = Field(default_factory=dict)
    write_mapping: dict[str, str] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    primary_identifier: str = "email"


class CRMConfigOut(CRMConfigIn):
    pass


class CRMTestOut(BaseModel):
    ok: bool
    status_code: int | None = None
    mapped: dict[str, Any] | None = None
    sample: Any | None = None
    error: str | None = None


class ProactiveConfigIn(BaseModel):
    metric_url: str | None = None
    threshold: int = 30


class FileOut(BaseModel):
    id: UUID
    filename: str
    status: str


class CustomerOut(BaseModel):
    tariff: str | None = None
    accounts_count: int | None = None
    views_trend: str | None = None
    raw: dict | None = None


class UpdateCustomerIn(BaseModel):
    tariff: str | None = None


class AgentToolIn(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    description: str = Field(min_length=10, max_length=1000)
    tool_type: str = Field(pattern=r"^(lookup|action)$")
    method: str = Field(default="GET", pattern=r"^(GET|POST|PATCH|PUT|DELETE)$")
    url_template: str = Field(min_length=1, max_length=2000)
    headers: dict[str, str] = Field(default_factory=dict)
    body_template: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    require_confirmation: bool = False
    enabled: bool = True


class AgentToolOut(AgentToolIn):
    id: UUID
    created_at: str

    class Config:
        from_attributes = True


class AgentToolLogOut(BaseModel):
    id: UUID
    tool_name: str
    user_id: str
    status: str
    request: dict | None = None
    response: Any | None = None
    error: str | None = None
    latency_ms: int | None = None
    created_at: str


# ---- Integrations upgrade schemas ----

class NativeConnectIn(BaseModel):
    provider: str = Field(pattern=r"^(shopify|woocommerce|stripe)$")
    credentials: dict[str, str] = Field(min_length=1)
    meta: dict[str, Any] = Field(default_factory=dict)


class NativeConnectOut(BaseModel):
    provider: str
    status: str
    meta: dict[str, Any]
    created_at: str
    updated_at: str


class WebhookConfigIn(BaseModel):
    incoming_url: str | None = None
    incoming_secret: str | None = None
    outgoing_url: str | None = None
    outgoing_secret: str | None = None
    field_mapping: dict[str, str] = Field(default_factory=dict)
    events: list[str] = Field(default_factory=list)
    enabled: bool = True


class WebhookConfigOut(WebhookConfigIn):
    created_at: str
    updated_at: str


class WriteBackConfigIn(BaseModel):
    type: str = Field(default="off", pattern=r"^(off|hubspot_note|webhook)$")
    hubspot_note_enabled: bool = False
    hubspot_task_on_escalation: bool = False
    webhook_url: str | None = None


class WriteBackConfigOut(WriteBackConfigIn):
    created_at: str
    updated_at: str


class IntegrationStatusOut(BaseModel):
    native_connectors: list[NativeConnectOut]
    webhook_config: WebhookConfigOut | None = None
    writeback_config: WriteBackConfigOut | None = None


class ChannelConfigIn(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


class ChannelConfigOut(BaseModel):
    channel_type: str
    label: str
    description: str
    status: str
    config_mask: dict[str, Any]
    last_error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
