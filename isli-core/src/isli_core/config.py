import os
import secrets
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV = os.getenv("ISLI_ENV", "development").lower()
IS_DEV = ENV in ("development", "dev", "local", "test")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore",
        env_file=os.getenv("ISLI_ENV_FILE", ".env"),
    )

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
    webhook_secrets: dict[str, str] = {
        "telegram": "telegram-secret",
        "whatsapp": "whatsapp-secret",
    }
    task_lease_minutes: int = 30
    workspace_base_path: str = "./workspaces" if IS_DEV else "/workspaces"

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
