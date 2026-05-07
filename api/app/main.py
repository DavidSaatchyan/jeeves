"""FastAPI entrypoint — wires all routers and creates DB tables on boot."""
from __future__ import annotations

import logging
import re

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from pathlib import Path

from . import admin, auth, dashboard_api, knowledge, routes_chat, routes_crm, routes_proactive, routes_tools, routes_mock, routes_integrations, routes_channels, routes_api_keys
from .channels import widget as widget_channel
from .config import get_settings
from .db import Base, engine
from .models import *  # noqa: F401,F403  # ensure models are registered

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")

_SENSITIVE_FIELDS = {
    "password", "token", "secret", "key", "authorization",
    "access_token", "refresh_token", "api_key", "credentials",
}


def _mask_request_log(data: dict) -> dict:
    """Return a copy of data with sensitive values replaced by ******."""
    out = {}
    for k, v in data.items():
        if isinstance(k, str) and any(s in k.lower() for s in _SENSITIVE_FIELDS):
            out[k] = "******"
        elif isinstance(v, dict):
            out[k] = _mask_request_log(v)
        elif isinstance(v, str) and len(v) > 100:
            out[k] = v[:100] + "…"
        else:
            out[k] = v
    return out

app = FastAPI(title="Jeeves — Universal AI Agent", version="1.0.0-mvp")

logger = logging.getLogger("jeeves")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all handler — return generic message, log details server-side."""
    logger.exception("Unhandled exception on %s %s", request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": "Invalid request body"},
    )

@app.middleware("http")
async def request_logger(request: Request, call_next):
    """Log request method, path, and masked body. Sensitive fields are redacted."""
    method = request.method
    path = request.url.path

    # Log masked body for POST/PUT/PATCH
    if method in ("POST", "PUT", "PATCH"):
        try:
            body = await request.json()
            masked = _mask_request_log(body)
            logger.info("%s %s body=%s", method, path, masked)
        except Exception:
            logger.info("%s %s", method, path)
    else:
        logger.info("%s %s", method, path)

    response = await call_next(request)
    return response


# CORS: widget is embedded on arbitrary customer sites, so widget endpoints allow all origins.
# API endpoints use a restrictive CORS policy.
_widget_paths = {"/widget.js", "/widget/chat", "/widget/inbox", "/widget/rating"}

@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Add security headers to every response."""
    response = await call_next(request)
    # HSTS — force HTTPS in production
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "0"  # rely on CSP instead
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store" if "/auth/" in str(request.url.path) else response.headers.get("Cache-Control", "no-cache")
    return response


@app.middleware("http")
async def dynamic_cors(request: Request, call_next):
    """Apply restrictive CORS for API endpoints, permissive for widget endpoints."""
    origin = request.headers.get("origin", "")
    path = request.url.path

    # Widget endpoints — allow any origin (needed for embedding)
    if path in _widget_paths or path.startswith("/widget"):
        response = await call_next(request)
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
        return response

    # API endpoints — restrictive CORS
    settings = get_settings()
    allowed = ["http://localhost:8000"]
    if settings.public_base_url and settings.public_base_url != "http://localhost:8000":
        allowed.append(settings.public_base_url)

    response = await call_next(request)
    if origin and origin in allowed:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
    return response


_MIGRATIONS = [
    # Sprint 1 (S1): knowledge/observability columns. Safe to re-run.
    "ALTER TABLE files ADD COLUMN IF NOT EXISTS content_hash varchar(64)",
    "CREATE INDEX IF NOT EXISTS ix_files_content_hash ON files(content_hash)",
    "ALTER TABLE files ADD COLUMN IF NOT EXISTS chunks_total integer NOT NULL DEFAULT 0",
    "ALTER TABLE files ADD COLUMN IF NOT EXISTS size_bytes integer NOT NULL DEFAULT 0",
    "ALTER TABLE files ADD COLUMN IF NOT EXISTS error text",
    "ALTER TABLE chat_logs ADD COLUMN IF NOT EXISTS sources jsonb",
    "ALTER TABLE crm_config ADD COLUMN IF NOT EXISTS provider varchar(32) NOT NULL DEFAULT 'custom_rest'",
    "ALTER TABLE crm_config ADD COLUMN IF NOT EXISTS capabilities jsonb",
    # Agent tools tables (created by SQLAlchemy, but migrations for safety)
    """CREATE TABLE IF NOT EXISTS agent_tools (
        id uuid PRIMARY KEY,
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        name varchar(64) NOT NULL,
        description text NOT NULL,
        tool_type varchar(16) NOT NULL,
        method varchar(8) NOT NULL DEFAULT 'GET',
        url_template text NOT NULL,
        headers jsonb,
        body_template jsonb,
        parameters jsonb,
        require_confirmation boolean NOT NULL DEFAULT false,
        enabled boolean NOT NULL DEFAULT true,
        created_at timestamp NOT NULL DEFAULT now()
    )""",
    """CREATE TABLE IF NOT EXISTS agent_tool_logs (
        id uuid PRIMARY KEY,
        tenant_id uuid NOT NULL,
        tool_id uuid REFERENCES agent_tools(id) ON DELETE SET NULL,
        tool_name varchar(64) NOT NULL,
        user_id text NOT NULL,
        status varchar(16) NOT NULL,
        request jsonb,
        response jsonb,
        error text,
        latency_ms integer,
        created_at timestamp NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_agent_tools_tenant ON agent_tools(tenant_id)",
    "CREATE INDEX IF NOT EXISTS ix_agent_tool_logs_tenant ON agent_tool_logs(tenant_id)",
    # Integrations upgrade (Sprint 2): new columns and tables.
    "ALTER TABLE crm_config ADD COLUMN IF NOT EXISTS primary_identifier varchar(32) NOT NULL DEFAULT 'email'",
    "ALTER TABLE chat_logs ADD COLUMN IF NOT EXISTS session_id uuid",
    "CREATE INDEX IF NOT EXISTS ix_chat_logs_session_id ON chat_logs(session_id)",
    "ALTER TABLE chat_logs ADD COLUMN IF NOT EXISTS extra_fields jsonb",
    """CREATE TABLE IF NOT EXISTS native_connectors (
        id uuid PRIMARY KEY,
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        provider varchar(32) NOT NULL,
        status varchar(16) NOT NULL DEFAULT 'connected',
        credentials text NOT NULL,
        meta jsonb,
        created_at timestamp NOT NULL DEFAULT now(),
        updated_at timestamp NOT NULL DEFAULT now(),
        CONSTRAINT uq_native_connectors_tenant_provider UNIQUE (tenant_id, provider)
    )""",
    "CREATE INDEX IF NOT EXISTS ix_native_connectors_tenant ON native_connectors(tenant_id)",
    """CREATE TABLE IF NOT EXISTS webhook_configs (
        tenant_id uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
        incoming_url text,
        incoming_secret text,
        outgoing_url text,
        outgoing_secret text,
        field_mapping jsonb,
        events jsonb,
        enabled boolean NOT NULL DEFAULT true,
        created_at timestamp NOT NULL DEFAULT now(),
        updated_at timestamp NOT NULL DEFAULT now()
    )""",
    """CREATE TABLE IF NOT EXISTS writeback_configs (
        tenant_id uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
        type varchar(32) NOT NULL DEFAULT 'off',
        hubspot_note_enabled boolean NOT NULL DEFAULT false,
        hubspot_task_on_escalation boolean NOT NULL DEFAULT false,
        webhook_url text,
        created_at timestamp NOT NULL DEFAULT now(),
        updated_at timestamp NOT NULL DEFAULT now()
    )""",
    # Omnichannel: channel tracking on chat_logs
    "ALTER TABLE chat_logs ADD COLUMN IF NOT EXISTS channel varchar(32) NOT NULL DEFAULT 'web_widget'",
    """CREATE TABLE IF NOT EXISTS api_keys (
        id uuid PRIMARY KEY,
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        name varchar(128) NOT NULL,
        key_hash varchar(64) NOT NULL UNIQUE,
        prefix varchar(8) NOT NULL,
        created_at timestamp NOT NULL DEFAULT now(),
        last_used_at timestamp
    )""",
    "CREATE INDEX IF NOT EXISTS ix_api_keys_tenant ON api_keys(tenant_id)",
    "CREATE INDEX IF NOT EXISTS ix_api_keys_hash ON api_keys(key_hash)",
    "ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS expires_at timestamp",
]


@app.on_event("startup")
def on_startup() -> None:
    # DEFAULT: auto-create tables. Alembic can be added later.
    Base.metadata.create_all(bind=engine)
    # Idempotent column additions for existing deployments.
    with engine.begin() as conn:
        from sqlalchemy import text as _t
        for stmt in _MIGRATIONS:
            try:
                conn.execute(_t(stmt))
            except Exception as e:
                logging.warning("startup migration failed (%s): %s", stmt, e)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


_LANDING = Path(__file__).parent / "templates" / "landing.html"


@app.get("/", response_class=HTMLResponse)
def landing():
    return _LANDING.read_text(encoding="utf-8")


_TERMS = Path(__file__).parent / "templates" / "terms.html"
_PRIVACY = Path(__file__).parent / "templates" / "privacy.html"


@app.get("/terms", response_class=HTMLResponse)
def terms():
    return _TERMS.read_text(encoding="utf-8")


@app.get("/privacy", response_class=HTMLResponse)
def privacy():
    return _PRIVACY.read_text(encoding="utf-8")


app.include_router(auth.router)
app.include_router(routes_chat.router)
app.include_router(knowledge.router)
app.include_router(routes_crm.router)
app.include_router(routes_proactive.router)
app.include_router(dashboard_api.router)
app.include_router(widget_channel.router)
app.include_router(routes_tools.router)
app.include_router(routes_mock.router)
app.include_router(admin.router)
app.include_router(routes_integrations.router)
app.include_router(routes_channels.router)
app.include_router(routes_api_keys.router)
