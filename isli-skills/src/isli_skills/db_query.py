"""Read-only SQL query skill with AST validation and schema scoping."""

import asyncio
import hashlib
import re
from typing import Any

import asyncpg
import sqlparse
import structlog
from fastapi import HTTPException

logger = structlog.get_logger()

# Statements that are never allowed, even inside CTEs or subqueries.
FORBIDDEN_KEYWORDS = {
    "insert",
    "update",
    "delete",
    "merge",
    "upsert",
    "create",
    "alter",
    "drop",
    "truncate",
    "grant",
    "revoke",
    "copy",
    "execute",
    "call",
    "begin",
    "commit",
    "rollback",
    "savepoint",
    "set",
    "show",
}

# Allowed top-level statement types
ALLOWED_STMT_TYPES = {"select"}

# Regex to catch multi-statement strings (anything after a semicolon that isn't whitespace/comment)
_MULTI_STMT_RE = re.compile(r";\s*[^\s\-/*]", re.IGNORECASE)


def _normalize_dsn(dsn: str) -> str:
    """Strip SQLAlchemy driver suffix (+asyncpg) so asyncpg accepts the DSN."""
    return re.sub(r"^(postgresql|postgres)\+asyncpg://", r"\1://", dsn, count=1, flags=re.IGNORECASE)


def _normalize_tokens(sql: str) -> set[str]:
    """Extract normalized token strings from SQL for keyword scanning."""
    parsed = sqlparse.parse(sql)
    tokens: set[str] = set()
    for stmt in parsed:
        for token in stmt.flatten():
            if token.ttype in (
                sqlparse.tokens.Keyword,
                sqlparse.tokens.Keyword.DML,
                sqlparse.tokens.Keyword.DDL,
                sqlparse.tokens.Keyword.TCL,
            ) or str(token).strip().lower() in FORBIDDEN_KEYWORDS:
                tokens.add(str(token).strip().lower())
    return tokens


def _get_statement_types(sql: str) -> set[str]:
    """Return the set of top-level statement types in the SQL string."""
    parsed = sqlparse.parse(sql)
    types: set[str] = set()
    for stmt in parsed:
        first_token = None
        for token in stmt.tokens:
            if not token.is_whitespace:
                first_token = token
                break
        if first_token is not None:
            types.add(str(first_token).strip().lower())
    return types


def _contains_forbidden_keywords(sql: str) -> bool:
    """True if any forbidden keyword appears anywhere in the SQL text."""
    tokens = _normalize_tokens(sql)
    return bool(tokens & FORBIDDEN_KEYWORDS)


def _contains_multi_statement(sql: str) -> bool:
    """True if the string appears to contain more than one statement."""
    # Remove trailing semicolons and whitespace, then check
    stripped = sql.strip().rstrip(";").strip()
    if not stripped:
        return False
    return bool(_MULTI_STMT_RE.search(stripped))


def _inject_or_clamp_limit(sql: str, max_rows: int) -> str:
    """Inject LIMIT if absent, or clamp existing LIMIT to max_rows."""
    parsed = sqlparse.parse(sql)
    if not parsed:
        return sql

    # Check if the last statement already has a LIMIT clause
    last_stmt = parsed[-1]
    has_limit = False
    for token in last_stmt.tokens:
        if token.ttype is sqlparse.tokens.Keyword and str(token).strip().lower() == "limit":
            has_limit = True
            break
        if isinstance(token, sqlparse.sql.Where) or isinstance(token, sqlparse.sql.IdentifierList):
            # sqlparse does not always expose LIMIT as a top-level token;
            # fallback to regex on the raw SQL
            pass

    raw_lower = str(last_stmt).lower()
    limit_match = re.search(r"\blimit\s+(\d+)\b", raw_lower)
    if limit_match:
        existing = int(limit_match.group(1))
        if existing > max_rows:
            # Clamp
            sql = re.sub(r"\bLIMIT\s+\d+\b", f"LIMIT {max_rows}", sql, count=1, flags=re.IGNORECASE)
            return sql
        return sql

    # No LIMIT found — append one
    sql = sql.rstrip().rstrip(";")
    sql = f"{sql} LIMIT {max_rows}"
    return sql


def _extract_schema_from_query(sql: str) -> set[str]:
    """Heuristic extraction of schema names from table references."""
    schemas: set[str] = set()
    # Match schema.table patterns
    for match in re.finditer(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\b', sql):
        schemas.add(match.group(1).lower())
    return schemas


def validate_query(
    sql: str,
    allowed_schemas: set[str] | None = None,
) -> str:
    """Validate SQL and return a sanitized / normalized version.

    Raises HTTPException(400) on any policy violation.
    """
    if not sql or not sql.strip():
        raise HTTPException(status_code=400, detail="Empty SQL query.")

    if _contains_multi_statement(sql):
        raise HTTPException(status_code=400, detail="Multi-statement queries are not allowed.")

    if _contains_forbidden_keywords(sql):
        raise HTTPException(status_code=400, detail="Query contains forbidden keywords. Only SELECT statements are permitted.")

    stmt_types = _get_statement_types(sql)
    if stmt_types - ALLOWED_STMT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported statement type(s): {stmt_types - ALLOWED_STMT_TYPES}. Only SELECT is allowed.")

    if allowed_schemas:
        referenced = _extract_schema_from_query(sql)
        invalid = referenced - {s.lower() for s in allowed_schemas}
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Query references schemas not in allow-list: {invalid}"
            )

    return sql


async def execute_query(
    sql: str,
    database_url: str,
    max_rows: int = 100,
    timeout_seconds: float = 15.0,
) -> dict[str, Any]:
    """Execute a validated read-only SQL query and return structured results.

    Returns:
        {
            "success": bool,
            "columns": list[str],
            "rows": list[list[Any]],
            "row_count": int,
            "truncated": bool,
            "execution_time_ms": float,
            "reference_id": str | None,
        }
    """
    reference_id = hashlib.sha256(f"{sql}:{asyncio.get_event_loop().time()}".encode()).hexdigest()[:12]

    # Inject/clamp LIMIT
    safe_sql = _inject_or_clamp_limit(sql, max_rows)
    truncated = safe_sql != sql.rstrip().rstrip(";")

    conn: asyncpg.Connection | None = None
    start = asyncio.get_event_loop().time()
    normalized_dsn = _normalize_dsn(database_url)
    try:
        conn = await asyncpg.connect(normalized_dsn, timeout=5.0)
        # Set read-only mode at connection level (PostgreSQL-specific)
        await conn.execute("SET TRANSACTION READ ONLY")
        rows = await conn.fetch(safe_sql, timeout=timeout_seconds)
        elapsed_ms = (asyncio.get_event_loop().time() - start) * 1000

        columns: list[str] = []
        result_rows: list[list[Any]] = []
        if rows:
            columns = list(rows[0].keys())
            result_rows = [list(row.values()) for row in rows]

        return {
            "success": True,
            "columns": columns,
            "rows": result_rows,
            "row_count": len(result_rows),
            "truncated": truncated,
            "execution_time_ms": round(elapsed_ms, 2),
            "reference_id": reference_id,
        }

    except asyncpg.PostgresError as exc:
        elapsed_ms = (asyncio.get_event_loop().time() - start) * 1000
        logger.error(
            "db_query.postgres_error",
            reference_id=reference_id,
            error_type=type(exc).__name__,
            detail=str(exc),
            execution_time_ms=round(elapsed_ms, 2),
        )
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "error": "Query execution failed. Check your SQL syntax or schema references.",
                "reference_id": reference_id,
            },
        )
    except asyncio.TimeoutError:
        logger.error("db_query.timeout", reference_id=reference_id, timeout=timeout_seconds)
        raise HTTPException(
            status_code=504,
            detail={
                "success": False,
                "error": f"Query timed out after {timeout_seconds}s.",
                "reference_id": reference_id,
            },
        )
    except Exception as exc:
        logger.error("db_query.unexpected_error", reference_id=reference_id, error=str(exc))
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": "An unexpected error occurred while executing the query.",
                "reference_id": reference_id,
            },
        )
    finally:
        if conn is not None:
            await conn.close()
