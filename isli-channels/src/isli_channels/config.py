import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_file=os.getenv("ISLI_ENV_FILE", ".env"))

    telegram_bot_token: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    redis_url: str = ""
    core_api_url: str = ""
    webhook_secret: str = ""
    otel_service_name: str = "isli-channels"


@lru_cache
def get_settings() -> Settings:
    return Settings()
