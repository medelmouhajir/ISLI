from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore",
        env_file=".env",
    )

    workspace_base_path: str = "./workspaces"
    jwt_secret: str = ""
    max_file_size_mb: int = 10
    max_workspace_size_mb: int = 100
    otel_service_name: str = "isli-workspace"


settings = Settings()
