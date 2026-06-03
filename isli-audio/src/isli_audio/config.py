import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_file=os.getenv("ISLI_ENV_FILE", ".env"))

    audio_stt_model: str = "whisper-tiny"
    audio_tts_model: str = "piper-en-us-lessac-medium"
    audio_language: str = "en"
    jwt_secret: str = ""
    otel_service_name: str = "isli-audio"
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    models_dir: str = "/app/models"


@lru_cache
def get_settings() -> Settings:
    return Settings()
