import os
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_file=os.getenv("ISLI_ENV_FILE", ".env"))

    isli_env: str = os.getenv("ISLI_ENV", "development")
    core_api_url: str = ""
    redis_url: str = ""
    skill_registry_token: str = ""
    otel_service_name: str = "isli-skills"
    jwt_secret: str = ""
    database_url: str = ""

    @field_validator("jwt_secret", mode="before")
    @classmethod
    def _read_secret_file(cls, v):
        if isinstance(v, str) and v.startswith("/run/secrets/"):
            try:
                return Path(v).read_text().strip()
            except FileNotFoundError:
                raise ValueError(f"Secret file not found: {v}")
        return v
    db_query_allowed_schemas: str = "public"  # comma-separated
    db_query_max_rows: int = 100
    db_query_timeout_seconds: float = 15.0
    browser_headless: bool = True
    browser_session_ttl: int = 600
    browser_session_dir: str = "/tmp/browser-sessions"
    browser_max_snapshot_chars: int = 8000
    browser_redis_url: str = ""
    browser_max_concurrent_sessions: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
