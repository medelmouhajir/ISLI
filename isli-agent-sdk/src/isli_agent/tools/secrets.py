from typing import Any

from isli_agent.client import CoreClient


def _get_tool_desc(name: str, default: str) -> str:
    try:
        from isli_agent.prompts_loader import get_prompts
        return get_prompts()["agent"]["tool_descriptions"].get(name, default)
    except Exception:
        return default


class SecretNotFoundError(Exception):
    """Raised when the requested secret does not exist."""


class SecretAccessError(Exception):
    """Raised when the agent is not authorized to access the secret."""


async def get_secret(
    agent_id: str,
    name: str,
    core_client: CoreClient,
) -> str:
    """Retrieve a secret value from the agent's secure vault by name."""
    payload: dict[str, Any] = {
        "agent_id": agent_id,
        "name": name,
    }
    resp = await core_client.client.post(
        "/v1/skills/get-secret/get",
        json=payload,
        headers=core_client._get_headers(),
    )
    if resp.status_code == 404:
        raise SecretNotFoundError(f"Secret '{name}' not found")
    if resp.status_code == 403:
        raise SecretAccessError(f"Access denied to secret '{name}'")
    resp.raise_for_status()
    data = resp.json()
    return data["value"]


GET_SECRET_DEF = {
    "type": "function",
    "function": {
        "name": "get_secret",
        "description": _get_tool_desc(
            "get_secret",
            "Retrieve a secret value from your secure vault by name. Use this to access API keys, database credentials, or tokens without hardcoding them.",
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the secret to retrieve (e.g., 'openai_api_key', 'db_password')",
                },
            },
            "required": ["name"],
        },
    },
}
