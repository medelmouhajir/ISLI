from typing import Any

from isli_agent.client import CoreClient


def _get_tool_desc(name: str, default: str) -> str:
    try:
        from isli_agent.prompts_loader import get_prompts
        return get_prompts()["agent"]["tool_descriptions"].get(name, default)
    except Exception:
        return default


class PackageInstallError(Exception):
    """Raised when a pip install operation fails."""


class PackageInvalidError(Exception):
    """Raised when the package list contains forbidden flags or invalid names."""


class PackageTimeoutError(Exception):
    """Raised when pip install exceeds the allowed execution time."""


async def pip_install(
    agent_id: str,
    packages: list[str],
    core_client: CoreClient,
    upgrade: bool = False,
) -> dict[str, Any]:
    """Install Python packages from PyPI into the agent's workspace."""
    payload: dict[str, Any] = {
        "agent_id": agent_id,
        "packages": packages,
        "upgrade": upgrade,
    }
    resp = await core_client.client.post(
        "/v1/skills/pip-install/install",
        json=payload,
        headers=core_client._get_headers(),
    )
    if resp.status_code == 400:
        raise PackageInvalidError(f"Invalid packages: {resp.json().get('detail', '')}")
    if resp.status_code == 408:
        raise PackageTimeoutError(f"Install timed out: {resp.json().get('detail', '')}")
    if resp.status_code == 500:
        raise PackageInstallError(f"Install failed: {resp.json().get('detail', '')}")
    resp.raise_for_status()
    return resp.json()


async def pip_list(
    agent_id: str,
    core_client: CoreClient,
) -> dict[str, Any]:
    """List Python packages installed in the agent's workspace."""
    resp = await core_client.client.post(
        "/v1/skills/pip-list/list",
        json={"agent_id": agent_id},
        headers=core_client._get_headers(),
    )
    if resp.status_code == 500:
        raise PackageInstallError(f"List failed: {resp.json().get('detail', '')}")
    resp.raise_for_status()
    return resp.json()


PIP_INSTALL_DEF = {
    "type": "function",
    "function": {
        "name": "pip_install",
        "description": _get_tool_desc(
            "pip_install",
            "Install Python packages from PyPI into the agent's workspace. Packages persist across restarts.",
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "packages": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of package names or specifiers to install (e.g., ['requests', 'pandas==2.0.0'])",
                },
                "upgrade": {
                    "type": "boolean",
                    "description": "Whether to upgrade existing packages (default: false)",
                },
            },
            "required": ["packages"],
        },
    },
}

PIP_LIST_DEF = {
    "type": "function",
    "function": {
        "name": "pip_list",
        "description": _get_tool_desc(
            "pip_list",
            "List Python packages installed in the agent's workspace via pip-install.",
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}
