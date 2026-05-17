import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_file=os.getenv("ISLI_ENV_FILE", ".env"))

    core_api_url: str = ""
    redis_url: str = ""
    skill_registry_token: str = ""
    otel_service_name: str = "isli-skills"
    jwt_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
