from typing import Any

from isli_agent.client import CoreClient


def _get_tool_desc(name: str, default: str) -> str:
    try:
        from isli_agent.prompts_loader import get_prompts
        return get_prompts()["agent"]["tool_descriptions"].get(name, default)
    except Exception:
        return default


async def db_query(
    agent_id: str,
    query: str,
    core_client: CoreClient,
    schema: str | None = None,
    max_rows: int = 50,
    max_cell_chars: int = 500,
    password: str | None = None,
    connection_string: str | None = None,
) -> dict[str, Any]:
    """Execute a read-only SQL query via the db-query skill and return structured tabular results."""
    payload: dict[str, Any] = {
        "agent_id": agent_id,
        "query": query,
        "max_rows": max_rows,
        "max_cell_chars": max_cell_chars,
    }
    if schema is not None:
        payload["schema"] = schema
    if password:
        payload["password"] = password
    if connection_string:
        payload["connection_string"] = connection_string
    resp = await core_client.client.post(
        "/v1/skills/db-query/query",
        json=payload,
        headers=core_client._get_headers(),
    )
    resp.raise_for_status()
    return resp.json()


DB_QUERY_DEF = {
    "type": "function",
    "function": {
        "name": "db_query",
        "description": _get_tool_desc(
            "db_query",
            "Run a read-only SQL query against the database. Returns structured tabular results. For credentials, pass [[secret:NAME]].",
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The SQL SELECT query to execute. Only SELECT statements are allowed.",
                },
                "schema": {
                    "type": "string",
                    "description": "Optional explicit schema to query. Defaults to the configured allow-list.",
                },
                "max_rows": {
                    "type": "integer",
                    "description": "Maximum rows to return (default 100, server-enforced cap).",
                    "default": 100,
                },
                "password": {
                    "type": "string",
                    "description": "Optional database password reference (e.g., [[secret:db_pass]]).",
                },
                "connection_string": {
                    "type": "string",
                    "description": "Optional full connection string reference (e.g., [[secret:db_url]]).",
                },
            },
            "required": ["query"],
        },
    },
}
