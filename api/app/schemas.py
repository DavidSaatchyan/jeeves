"""Pydantic request/response schemas."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    tenant_name: str


class RefreshIn(BaseModel):
    refresh_token: str


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
    escalated: bool = False
    resolution: str | None = None


class WidgetChatIn(BaseModel):
    tenant_id: UUID
    user_id: str = Field(min_length=1, max_length=256)
    message: str = Field(min_length=1, max_length=4000)
    channel: str = "web_widget"
    extra_fields: dict[str, Any] = Field(default_factory=dict)


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
