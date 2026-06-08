import os
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_file=os.getenv("ISLI_ENV_FILE", ".env"))

    isli_env: str = os.getenv("ISLI_ENV", "development")
    telegram_bot_token: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    redis_url: str = ""
    core_api_url: str = ""
    webhook_secret: str = ""
    jwt_secret: str = ""
    blob_store_db: int = 10
    otel_service_name: str = "isli-channels"

    @field_validator("jwt_secret", mode="before")
    @classmethod
    def _read_secret_file(cls, v):
        if isinstance(v, str) and v.startswith("/run/secrets/"):
            try:
                return Path(v).read_text().strip()
            except FileNotFoundError as exc:
                raise ValueError(f"Secret file not found: {v}") from exc
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
