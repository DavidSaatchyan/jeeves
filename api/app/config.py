"""Runtime config: env vars + config.yaml."""
from __future__ import annotations

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
    access_token_ttl_minutes: int = 60
    refresh_token_ttl_days: int = 30
    public_base_url: str = "http://localhost:8000"
    knowledge_dir: str = "/app/knowledge"
    config_path: str = "/app/config.yaml"
    pabau_api_key: str = ""
    cliniko_api_key: str = ""
    cliniko_user_agent: str = "Jeeves (devs@jeeves.ai)"
    azure_api_key: str = ""
    azure_endpoint: str = ""
    azure_deployment: str = ""
    azure_api_version: str = "2024-10-21"
    bedrock_access_key: str = ""
    bedrock_secret_key: str = ""
    bedrock_region: str = "us-east-1"
    bedrock_model_id: str = "anthropic.claude-3-haiku-20240307-v1:0"
    fernet_key: str = ""
    facebook_app_id: str = ""
    facebook_app_secret: str = ""
    facebook_redirect_uri: str = ""
    # Compliance / data governance
    compliance_gdpr_enabled: bool = True
    compliance_hipaa_enabled: bool = False
    compliance_audit_retention_days: int = 1095        # 3 years
    compliance_consent_auto_renew_days: int = 365
    compliance_data_residency: str = "auto"             # auto | eu | us
    consent_required_channels: str = "whatsapp,widget"
    phi_log_level: str = "INFO"
    data_retention_default_days: int = 730

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
