"""Centralized startup validation for production safety."""

import os
import structlog

logger = structlog.get_logger()

WEAK_SECRETS = {
    "change-me",
    "change-me-in-production",
    "dev-secret",
    "secret",
    "password",
    "admin",
    "123456",
    "default",
}


def validate_startup_secrets() -> None:
    """Fail fast if any required production secret is missing or weak."""
    from .config import get_settings
    settings = get_settings()
    env = os.getenv("ISLI_ENV", "development").lower()
    is_prod = env not in ("development", "dev", "local", "test")

    jwt_secret = settings.jwt_secret or os.getenv("JWT_SECRET", "")
    if not jwt_secret or len(jwt_secret) < 32 or jwt_secret.lower() in WEAK_SECRETS:
        raise RuntimeError(
            "JWT_SECRET is missing, shorter than 32 characters, or is a known weak value. "
            "Set a strong secret before starting the service."
        )

    db_url = settings.database_url or os.getenv("DATABASE_URL", "")
    if is_prod and "sqlite" in db_url.lower():
        raise RuntimeError(
            "SQLite is not allowed in production. Set DATABASE_URL to a PostgreSQL connection string."
        )

    redis_url = settings.redis_url or os.getenv("REDIS_URL", "")
    if is_prod and "fakeredis" in redis_url.lower():
        raise RuntimeError(
            "fakeredis is not allowed in production. Set REDIS_URL to a real Redis connection string."
        )

    enc_key = settings.pii_encryption_key or os.getenv("PII_ENCRYPTION_KEY", "")
    if is_prod and not enc_key:
        raise RuntimeError("PII_ENCRYPTION_KEY must be set in production.")
    if enc_key and len(enc_key.encode()) < 32:
        raise RuntimeError("PII_ENCRYPTION_KEY must be at least 32 bytes of entropy.")

    fallback_model = os.getenv("KEEPER_FALLBACK_MODEL", "")
    if fallback_model and fallback_model.startswith(("anthropic", "openai")):
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        openai_key = os.getenv("OPENAI_API_KEY", "")
        if not anthropic_key and not openai_key:
            logger.warning(
                "startup.no_cloud_api_key",
                fallback_model=fallback_model,
                message="Cloud fallback is configured but no ANTHROPIC_API_KEY or OPENAI_API_KEY is set.",
            )

    logger.info("startup.validation_passed", production=is_prod)
