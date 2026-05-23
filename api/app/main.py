"""FastAPI entrypoint — wires all routers and applies Alembic migrations on boot."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from alembic.config import Config
from alembic import command
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.exceptions import RequestValidationError

from . import admin, auth, integrations_routes, knowledge, routes_chat
from .integrations import webhooks as webhooks_router
from .channels import widget as widget_channel
from .config import get_settings
from .db import engine
from sqlalchemy import text

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


def _run_alembic_migrations() -> None:
    """Apply Alembic migrations on startup. Uses the alembic/ directory from the api package."""
    alembic_cfg = Config(Path(__file__).parent.parent / "alembic.ini")
    alembic_cfg.set_main_option("script_location", str(Path(__file__).parent.parent / "alembic"))
    try:
        command.upgrade(alembic_cfg, "head")
        logging.info("Alembic migrations applied successfully")
    except Exception as e:
        error_str = str(e).lower()
        if "already exists" in error_str or "duplicate" in error_str:
            from sqlalchemy import inspect
            inspector = inspect(engine)
            if "tenants" in inspector.get_table_names():
                command.stamp(alembic_cfg, "head")
                logging.info("Existing DB detected — stamped alembic to head without re-running migrations")
            else:
                logging.exception("Alembic migration failed — unexpected duplicate table without tenants")
        elif "can't render element of type" in error_str or "jsonb" in error_str.lower():
            # Dev fallback: create all tables directly (SQLite compat with JSON instead of JSONB)
            from .models import Base
            Base.metadata.create_all(bind=engine)
            logging.info("Dev mode: created all tables via Base.metadata.create_all (bypassed alembic)")
        else:
            logging.exception("Alembic migration failed — check database connectivity and migration files")


@app.on_event("startup")
def on_startup() -> None:
    _run_alembic_migrations()
    from .channels.registry import build_channel_cache
    from .core.workflows import init_workflows
    from .db import SessionLocal
    db = SessionLocal()
    try:
        build_channel_cache(db)
        init_workflows()
    finally:
        db.close()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

@app.get("/health/ready")
def health_ready() -> dict:
    import os
    return {"status": "ok", "workers": {"scheduler": os.environ.get("WORKER_TYPE", "api") == "scheduler"}}

@app.get("/health/db")
def health_db() -> dict:
    from .db import SessionLocal
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


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
app.include_router(widget_channel.router)
app.include_router(admin.router)
app.include_router(integrations_routes.router)
app.include_router(webhooks_router.router)
