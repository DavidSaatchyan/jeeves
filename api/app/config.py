"""Runtime config: env vars + config.yaml."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://jeeves:jeeves123@postgres:5432/jeeves"
    redis_url: str = ""
    chroma_url: str = ""
    chroma_path: str = ""
    openai_api_key: str = ""
    jwt_secret: str = "dev-secret-change-me-min-32-chars-long!"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60 * 24 * 7  # 7 days per FR-1.3
    refresh_token_ttl_days: int = 30
    public_base_url: str = "http://localhost:8000"
    knowledge_dir: str = "/app/knowledge"
    config_path: str = "/app/config.yaml"
    hubspot_client_id: str = ""
    hubspot_client_secret: str = ""
    hubspot_redirect_uri: str = "http://localhost:8000/crm/oauth/hubspot/callback"
    fernet_key: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


@lru_cache(maxsize=1)
def get_yaml_config() -> dict:
    settings = get_settings()
    path = Path(settings.config_path)
    if not path.exists():
        # DEFAULT: fallback empty dict if config.yaml is absent
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
