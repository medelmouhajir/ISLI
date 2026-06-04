"""Centralized startup validation for production safety."""

import os
from pathlib import Path
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


def _resolve_secret(value: str) -> str:
    """If value is a secret file path, read its contents."""
    if value.startswith("/run/secrets/"):
        try:
            return Path(value).read_text().strip()
        except FileNotFoundError:
            return value
    return value


def validate_startup_secrets() -> None:
    """Fail fast if any required production secret is missing or weak."""
    env = os.getenv("ISLI_ENV", "development").lower()
    is_prod = env not in ("development", "dev", "local", "test")

    # Read directly from os.environ so mutations are respected (e.g. in tests).
    # Resolve Docker Compose secret file references.
    jwt_secret = _resolve_secret(os.getenv("JWT_SECRET", ""))
    if not jwt_secret or len(jwt_secret) < 32 or jwt_secret.lower() in WEAK_SECRETS:
        raise RuntimeError(
            "JWT_SECRET is missing, shorter than 32 characters, or is a known weak value. "
            "Set a strong secret before starting the service."
        )

    db_url = os.getenv("DATABASE_URL", "")
    if is_prod and "sqlite" in db_url.lower():
        raise RuntimeError(
            "SQLite is not allowed in production. Set DATABASE_URL to a PostgreSQL connection string."
        )

    redis_url = os.getenv("REDIS_URL", "")
    if is_prod and "fakeredis" in redis_url.lower():
        raise RuntimeError(
            "fakeredis is not allowed in production. Set REDIS_URL to a real Redis connection string."
        )

    enc_key = _resolve_secret(os.getenv("PII_ENCRYPTION_KEY", ""))
    if is_prod and not enc_key:
        raise RuntimeError("PII_ENCRYPTION_KEY must be set in production.")
    if enc_key and len(enc_key.encode()) < 32:
        raise RuntimeError("PII_ENCRYPTION_KEY must be at least 32 bytes of entropy.")

    logger.info("startup.validation_passed", production=is_prod)
