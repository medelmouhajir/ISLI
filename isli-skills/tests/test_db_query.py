"""Tests for the db-query skill (SQL validation and execution)."""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException

from isli_skills.db_query import validate_query, execute_query, _normalize_dsn, _inject_or_clamp_limit


class TestValidateQuery:
    def test_valid_select(self):
        # Should not raise
        result = validate_query("SELECT * FROM users")
        assert result == "SELECT * FROM users"

    def test_valid_select_with_limit(self):
        result = validate_query("SELECT id, name FROM agents LIMIT 10")
        assert "LIMIT 10" in result

    def test_rejects_insert(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_query("INSERT INTO users (name) VALUES ('x')")
        assert exc_info.value.status_code == 400
        assert "forbidden" in str(exc_info.value.detail).lower()

    def test_rejects_update(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_query("UPDATE users SET name = 'x'")
        assert exc_info.value.status_code == 400

    def test_rejects_delete(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_query("DELETE FROM users WHERE id = 1")
        assert exc_info.value.status_code == 400

    def test_rejects_drop(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_query("DROP TABLE users")
        assert exc_info.value.status_code == 400

    def test_rejects_alter(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_query("ALTER TABLE users ADD COLUMN foo TEXT")
        assert exc_info.value.status_code == 400

    def test_rejects_create(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_query("CREATE TABLE foo (id INT)")
        assert exc_info.value.status_code == 400

    def test_rejects_multi_statement(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_query("SELECT 1; SELECT 2")
        assert "multi-statement" in str(exc_info.value.detail).lower()

    def test_rejects_empty(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_query("")
        assert "empty" in str(exc_info.value.detail).lower()

    def test_allows_schema_qualified_table(self):
        result = validate_query("SELECT * FROM public.users LIMIT 5")
        assert result is not None

    def test_rejects_forbidden_keyword_case_insensitive(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_query("GRANT ALL ON users TO public")
        assert exc_info.value.status_code == 400
        assert "forbidden" in str(exc_info.value.detail).lower()

    def test_rejects_unsupported_statement_type(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_query("EXPLAIN SELECT * FROM users")
        assert exc_info.value.status_code == 400
        assert "unsupported" in str(exc_info.value.detail).lower()


class TestNormalizeDsn:
    def test_strip_asyncpg_suffix(self):
        assert _normalize_dsn("postgresql+asyncpg://user:pass@host/db") == "postgresql://user:pass@host/db"

    def test_no_change_for_plain_postgresql(self):
        assert _normalize_dsn("postgresql://user:pass@host/db") == "postgresql://user:pass@host/db"

    def test_no_change_for_postgres(self):
        assert _normalize_dsn("postgres://user:pass@host/db") == "postgres://user:pass@host/db"


class TestInjectOrClampLimit:
    def test_injects_limit_when_missing(self):
        sql = "SELECT * FROM agents"
        result = _inject_or_clamp_limit(sql, 100)
        assert "LIMIT 100" in result

    def test_clamps_over_limit(self):
        sql = "SELECT * FROM agents LIMIT 500"
        result = _inject_or_clamp_limit(sql, 100)
        assert "LIMIT 100" in result
        assert "LIMIT 500" not in result

    def test_preserves_under_limit(self):
        sql = "SELECT * FROM agents LIMIT 50"
        result = _inject_or_clamp_limit(sql, 100)
        assert "LIMIT 50" in result


class TestExecuteQuery:
    @pytest.mark.asyncio
    async def test_success(self):
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [
            {"id": 1, "name": "agent-a"},
            {"id": 2, "name": "agent-b"},
        ]
        mock_conn.close = AsyncMock()

        with patch("isli_skills.db_query.asyncpg.connect", return_value=mock_conn):
            result = await execute_query(
                "SELECT id, name FROM agents LIMIT 2",
                "postgresql://user:pass@host/db",
                max_rows=10,
                timeout_seconds=5,
            )

        assert result["success"] is True
        assert result["row_count"] == 2
        assert len(result["rows"]) == 2
        assert result["rows"][0] == [1, "agent-a"]  # list values, not dict
        mock_conn.fetch.assert_awaited_once()
        mock_conn.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_error_sanitizes_dsn(self):
        import asyncpg
        mock_conn = AsyncMock()
        mock_conn.fetch.side_effect = asyncpg.PostgresError("syntax error at or near 'SELECT'")
        mock_conn.close = AsyncMock()

        with patch("isli_skills.db_query.asyncpg.connect", return_value=mock_conn):
            with pytest.raises(HTTPException) as exc_info:
                await execute_query(
                    "SELECT * FROM bad_syntax",
                    "postgresql://user:secret@host/db",
                    max_rows=10,
                    timeout_seconds=5,
                )

        assert exc_info.value.status_code == 400
        detail = str(exc_info.value.detail)
        assert "secret" not in detail
        assert "reference_id" in detail

    @pytest.mark.asyncio
    async def test_generic_error_returns_500(self):
        mock_conn = AsyncMock()
        mock_conn.fetch.side_effect = RuntimeError("something exploded")
        mock_conn.close = AsyncMock()

        with patch("isli_skills.db_query.asyncpg.connect", return_value=mock_conn):
            with pytest.raises(HTTPException) as exc_info:
                await execute_query(
                    "SELECT * FROM agents",
                    "postgresql://user:pass@host/db",
                    max_rows=10,
                    timeout_seconds=5,
                )

        assert exc_info.value.status_code == 500
        assert "unexpected" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_row_limit_clamping(self):
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = [{"id": i} for i in range(15)]
        mock_conn.close = AsyncMock()

        with patch("isli_skills.db_query.asyncpg.connect", return_value=mock_conn):
            result = await execute_query(
                "SELECT id FROM agents",
                "postgresql://user:pass@host/db",
                max_rows=10,
                timeout_seconds=5,
            )

        assert result["success"] is True
        assert result["row_count"] == 15  # mock returns 15; LIMIT is in SQL but mock ignores it
        # Ensure the query passed to asyncpg had LIMIT injected
        call_args = mock_conn.fetch.await_args
        assert "LIMIT 10" in str(call_args[0][0])

    @pytest.mark.asyncio
    async def test_timeout(self):
        mock_conn = AsyncMock()
        mock_conn.fetch.side_effect = asyncio.TimeoutError()
        mock_conn.close = AsyncMock()

        with patch("isli_skills.db_query.asyncpg.connect", return_value=mock_conn):
            with pytest.raises(HTTPException) as exc_info:
                await execute_query(
                    "SELECT pg_sleep(10)",
                    "postgresql://user:pass@host/db",
                    max_rows=10,
                    timeout_seconds=1,
                )

        assert exc_info.value.status_code == 504
        assert "timed out" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_postgres_error(self):
        import asyncpg
        mock_conn = AsyncMock()
        mock_conn.fetch.side_effect = asyncpg.PostgresError("relation does not exist")
        mock_conn.close = AsyncMock()

        with patch("isli_skills.db_query.asyncpg.connect", return_value=mock_conn):
            with pytest.raises(HTTPException) as exc_info:
                await execute_query(
                    "SELECT * FROM nonexistent_table",
                    "postgresql://user:pass@host/db",
                    max_rows=10,
                    timeout_seconds=5,
                )

        assert exc_info.value.status_code == 400
        assert "reference_id" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_empty_result_set(self):
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = []
        mock_conn.close = AsyncMock()

        with patch("isli_skills.db_query.asyncpg.connect", return_value=mock_conn):
            result = await execute_query(
                "SELECT * FROM agents WHERE 1=0",
                "postgresql://user:pass@host/db",
                max_rows=10,
                timeout_seconds=5,
            )

        assert result["success"] is True
        assert result["row_count"] == 0
        assert result["rows"] == []
        assert result["columns"] == []
