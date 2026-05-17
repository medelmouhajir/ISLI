import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_file=os.getenv("ISLI_ENV_FILE", ".env"))

    ollama_host: str = ""
    ollama_embed_model: str = "nomic-embed-text"
    ollama_gen_model: str = "qwen2.5:7b"
    keeper_fallback_model: str = ""
    keeper_identity: str = "isli-keeper"
    ollama_api_key: str = ""
    database_url: str = ""
    chroma_host: str = "http://localhost:8000"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    otel_service_name: str = "isli-keeper"
    jwt_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
