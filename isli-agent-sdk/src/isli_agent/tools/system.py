from datetime import datetime, timezone
from typing import Any
from isli_agent.client import CoreClient


def get_current_datetime(format: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Return the current UTC date and time as a formatted string."""
    return datetime.now(timezone.utc).strftime(format)


async def shell_exec(agent_id: str, command: str, core_client: CoreClient) -> dict[str, Any]:
    """Execute a shell command via the shell-exec skill."""
    resp = await core_client.client.post(
        "/v1/skills/shell-exec/exec",
        json={"agent_id": agent_id, "command": command},
        headers=core_client._get_headers(),
    )
    resp.raise_for_status()
    return resp.json()


DATETIME_DEF = {
    "type": "function",
    "function": {
        "name": "get_current_datetime",
        "description": "Return the current UTC date and time.",
        "parameters": {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "description": "strftime format string (default: %Y-%m-%d %H:%M:%S)",
                }
            },
            "required": [],
        },
    },
}

SHELL_EXEC_DEF = {
    "type": "function",
    "function": {
        "name": "shell_exec",
        "description": "Execute a shell command in a sandboxed environment.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                }
            },
            "required": ["command"],
        },
    },
}
