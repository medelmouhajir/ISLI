from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore",
        env_file=".env",
    )

    isli_env: str = "development"
    workspace_base_path: str = "./workspaces"
    jwt_secret: str = ""
    max_file_size_mb: int = 10
    max_workspace_size_mb: int = 100
    otel_service_name: str = "isli-workspace"

    @field_validator("jwt_secret", mode="before")
    @classmethod
    def _read_secret_file(cls, v):
        if isinstance(v, str) and v.startswith("/run/secrets/"):
            try:
                return Path(v).read_text().strip()
            except FileNotFoundError:
                raise ValueError(f"Secret file not found: {v}")
        return v


settings = Settings()
