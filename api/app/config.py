"""Runtime config: env vars + config.yaml."""
from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings


def _normalize_redis_url(url: str) -> str:
    """Ensure rediss:// URLs include ssl_cert_reqs for redis-py / Kombu."""
    if url and url.startswith("rediss://") and "ssl_cert_reqs" not in url:
        sep = "&" if "?" in url else "?"
        return url + sep + "ssl_cert_reqs=required"
    return url


class Settings(BaseSettings):
    database_url: str
    redis_url: str = ""
    chroma_url: str = ""
    chroma_path: str = ""
    openai_api_key: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    public_base_url: str = "http://localhost:8000"
    knowledge_dir: str = "/app/knowledge"
    config_path: str = "/app/config.yaml"
    hubspot_client_id: str = ""
    hubspot_client_secret: str = ""
    hubspot_redirect_uri: str = "http://localhost:8000/crm/oauth/hubspot/callback"
    fernet_key: str = ""
    sendgrid_api_key: str = ""
    resend_api_key: str = ""
    shopify_shop: str = ""
    shopify_access_token: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


_REQUIRED_SECRETS = ["database_url", "openai_api_key", "jwt_secret"]


def _validate_secrets(settings: Settings) -> None:
    """Crash on startup if required secrets are missing or use known defaults."""
    unsafe_defaults = {
        "database_url": "postgresql+psycopg2://jeeves:jeeves123",
        "jwt_secret": "dev-secret-change-me",
    }
    for key in _REQUIRED_SECRETS:
        value = getattr(settings, key, "")
        if not value:
            print(f"[startup] FATAL: {key} is not set", file=sys.stderr, flush=True)
            sys.exit(1)
        for unsafe in unsafe_defaults.values():
            if value.startswith(unsafe):
                print(f"[startup] FATAL: {key} uses a known default value — set a strong secret", file=sys.stderr, flush=True)
                sys.exit(1)

    # Validate JWT secret minimum length
    if len(settings.jwt_secret) < 32:
        print("[startup] FATAL: jwt_secret must be at least 32 characters", file=sys.stderr, flush=True)
        sys.exit(1)

    # Validate Fernet key if encryption features will be used
    if settings.fernet_key and len(settings.fernet_key) < 32:
        print("[startup] WARNING: fernet_key is set but may be too weak (recommended: 32+ chars)", file=sys.stderr, flush=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.redis_url = _normalize_redis_url(settings.redis_url)
    _validate_secrets(settings)
    return settings


@lru_cache(maxsize=1)
def get_yaml_config() -> dict:
    settings = get_settings()
    path = Path(settings.config_path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
