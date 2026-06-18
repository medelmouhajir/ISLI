import os
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_file=os.getenv("ISLI_ENV_FILE", ".env"))

    isli_env: str = os.getenv("ISLI_ENV", "development")
    ollama_host: str = ""
    ollama_embed_model: str = "nomic-embed-text"
    ollama_gen_model: str = "qwen3:1.7b"
    ollama_think: bool = False
    keeper_fallback_model: str = ""
    keeper_identity: str = "isli-keeper"
    ollama_api_key: str = ""
    database_url: str = ""
    chroma_host: str = "http://localhost:8000"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    otel_service_name: str = "isli-keeper"
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    jwt_secret: str = ""

    @field_validator("jwt_secret", mode="before")
    @classmethod
    def _read_secret_file(cls, v):
        if isinstance(v, str) and v.startswith("/run/secrets/"):
            try:
                return Path(v).read_text().strip()
            except FileNotFoundError:
                raise ValueError(f"Secret file not found: {v}")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
