import os
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV = os.getenv("ISLI_ENV", "development").lower()
IS_DEV = ENV in ("development", "dev", "local", "test")


def _read_secret_file(v):
    if isinstance(v, str) and v.startswith("/run/secrets/"):
        try:
            return Path(v).read_text().strip()
        except FileNotFoundError as exc:
            raise ValueError(f"Secret file not found: {v}") from exc
    return v


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore",
        env_file=os.getenv("ISLI_ENV_FILE", ".env"),
    )

    isli_env: str = os.getenv("ISLI_ENV", "development")

    # In development, safe defaults are acceptable. In production, these must be set.
    database_url: str = "sqlite+aiosqlite:///./isli_dev.db" if IS_DEV else ""
    redis_url: str = "fakeredis://localhost" if IS_DEV else ""
    jwt_secret: str = secrets.token_urlsafe(32) if IS_DEV else ""
    admin_api_key: str = "isli-admin-dev-key" if IS_DEV else ""
    keeper_url: str = "http://localhost:8001"
    core_api_url: str = "http://localhost:8000"
    channels_url: str = "http://localhost:8002"
    workspace_url: str = "http://localhost:8300" if IS_DEV else "http://workspace:8300"
    otel_service_name: str = "isli-core"
    cors_origins: str = ""
    tls_cert_path: str = ""
    tls_key_path: str = ""
    pii_encryption_key: str = secrets.token_urlsafe(32) if IS_DEV else ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    # Channels adapter signs all webhooks with the single WEBHOOK_SECRET env var.
    # Core must use the same value for every channel it verifies.
    _webhook_secret: str = os.getenv("WEBHOOK_SECRET") or "telegram-secret"
    webhook_secrets: dict[str, str] = {
        "telegram": _webhook_secret,
        "whatsapp": _webhook_secret,
    }
    task_lease_minutes: int = 30
    workspace_base_path: str = "./workspaces" if IS_DEV else "/workspaces"
    agent_runner_image: str = "isli-agent-runner:latest"
    agent_network: str = "isli_isli"
    agent_sdk_host_path: str | None = None
    agent_runner_build_context: str | None = None
    default_local_model: str = "qwen3:1.7b"
    audio_url: str = "http://localhost:8400"
    installed_skills_path: str = "./data/installed_skills" if IS_DEV else "/data/installed_skills"
    blob_store_db: int = 10

    # Web Push VAPID Keys
    vapid_private_key: str = ""
    vapid_public_key: str = ""
    vapid_claims_email: str = "admin@isli-ai.local"

    @field_validator("jwt_secret", "admin_api_key", "pii_encryption_key", mode="before")
    @classmethod
    def _read_secret_file(cls, v):
        if isinstance(v, str) and v.startswith("/run/secrets/"):
            try:
                return Path(v).read_text().strip()
            except FileNotFoundError as exc:
                raise ValueError(f"Secret file not found: {v}") from exc
        return v

    @model_validator(mode="after")
    def _validate(self):
        weak_secrets = {"change-me", "dev-secret", "secret", "password", "admin"}
        if not self.jwt_secret or len(self.jwt_secret) < 32 or self.jwt_secret.lower() in weak_secrets:
            raise ValueError("jwt_secret must be at least 32 characters and not a common weak value")

        if not self.database_url:
            raise ValueError("database_url is required")
        if not IS_DEV and "sqlite" in self.database_url.lower():
            raise ValueError("SQLite is not allowed in production (ISLI_ENV=production). Use PostgreSQL.")

        if not self.redis_url:
            raise ValueError("redis_url is required")
        if not IS_DEV and "fakeredis" in self.redis_url.lower():
            raise ValueError("fakeredis is not allowed in production (ISLI_ENV=production). Use real Redis.")

        if not IS_DEV and not self.pii_encryption_key:
            raise ValueError("pii_encryption_key is required in production")
        if self.pii_encryption_key and len(self.pii_encryption_key.encode()) < 32:
            raise ValueError("pii_encryption_key must be at least 32 bytes of entropy")

        if not IS_DEV and not self.admin_api_key:
            raise ValueError("admin_api_key is required in production. Set ADMIN_API_KEY in your environment.")

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
