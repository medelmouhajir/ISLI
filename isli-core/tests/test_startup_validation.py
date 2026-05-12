"""Tests for startup validation logic."""

import os

import pytest

from isli_core.startup_validation import validate_startup_secrets


class TestStartupValidation:
    def test_weak_jwt_secret_raises(self):
        os.environ["JWT_SECRET"] = "short"
        with pytest.raises(RuntimeError) as exc:
            validate_startup_secrets()
        assert "JWT_SECRET" in str(exc.value)

    def test_common_weak_jwt_raises(self):
        os.environ["JWT_SECRET"] = "change-me-in-production"
        with pytest.raises(RuntimeError) as exc:
            validate_startup_secrets()
        assert "JWT_SECRET" in str(exc.value)

    def test_strong_jwt_passes(self):
        os.environ["JWT_SECRET"] = "a" * 32
        os.environ["DATABASE_URL"] = "postgresql+asyncpg://localhost/db"
        os.environ["REDIS_URL"] = "redis://localhost:6379"
        os.environ["PII_ENCRYPTION_KEY"] = "b" * 32
        # Should not raise
        validate_startup_secrets()

    def test_sqlite_in_production_raises(self):
        os.environ["JWT_SECRET"] = "a" * 32
        os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"
        os.environ["REDIS_URL"] = "redis://localhost:6379"
        os.environ["PII_ENCRYPTION_KEY"] = "b" * 32
        os.environ["ISLI_ENV"] = "production"
        try:
            with pytest.raises(RuntimeError) as exc:
                validate_startup_secrets()
            assert "SQLite" in str(exc.value)
        finally:
            del os.environ["ISLI_ENV"]

    def test_fakeredis_in_production_raises(self):
        os.environ["JWT_SECRET"] = "a" * 32
        os.environ["DATABASE_URL"] = "postgresql+asyncpg://localhost/db"
        os.environ["REDIS_URL"] = "fakeredis://localhost"
        os.environ["PII_ENCRYPTION_KEY"] = "b" * 32
        os.environ["ISLI_ENV"] = "production"
        try:
            with pytest.raises(RuntimeError) as exc:
                validate_startup_secrets()
            assert "fakeredis" in str(exc.value)
        finally:
            del os.environ["ISLI_ENV"]

    def test_missing_encryption_key_in_production_raises(self):
        os.environ["JWT_SECRET"] = "a" * 32
        os.environ["DATABASE_URL"] = "postgresql+asyncpg://localhost/db"
        os.environ["REDIS_URL"] = "redis://localhost:6379"
        if "PII_ENCRYPTION_KEY" in os.environ:
            del os.environ["PII_ENCRYPTION_KEY"]
        os.environ["ISLI_ENV"] = "production"
        try:
            with pytest.raises(RuntimeError) as exc:
                validate_startup_secrets()
            assert "PII_ENCRYPTION_KEY" in str(exc.value)
        finally:
            del os.environ["ISLI_ENV"]
