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
    blob_store_db: int = 10

    # Shell Execution (Sandbox)
    shell_exec_image: str = "alpine:latest"
    shell_exec_mem_limit: str = "256m"
    shell_exec_cpu_limit: float = 1.0
    shell_exec_timeout_default: int = 30
    shell_exec_timeout_max: int = 300
    shell_exec_output_limit: int = 65536
    workspace_base_path: str = "/workspaces"


@lru_cache
def get_settings() -> Settings:
    return Settings()
