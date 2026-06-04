import os
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_file=os.getenv("ISLI_ENV_FILE", ".env"))

    isli_env: str = os.getenv("ISLI_ENV", "development")
    audio_stt_model: str = "whisper-tiny"
    audio_tts_model: str = "piper-en-us-lessac-medium"
    audio_language: str = "en"
    jwt_secret: str = ""
    otel_service_name: str = "isli-audio"
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    models_dir: str = "/app/models"

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
