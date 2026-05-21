import json
from typing import Any

from isli_agent.client import CoreClient


def _get_tool_desc(name: str, default: str) -> str:
    try:
        from isli_agent.prompts_loader import get_prompts
        return get_prompts()["agent"]["tool_descriptions"].get(name, default)
    except Exception:
        return default


class WorkspacePathError(Exception):
    """Raised when a path is blocked by the workspace sandbox (traversal, not found, etc.)."""


class WorkspaceQuotaError(Exception):
    """Raised when a file or workspace quota is exceeded."""


class WorkspaceNotFoundError(Exception):
    """Raised when the requested file or directory does not exist."""


class WorkspacePermissionError(Exception):
    """Raised when the operation is not allowed on the given path (e.g., deleting a directory)."""


async def file_read(agent_id: str, path: str, core_client: CoreClient) -> dict[str, Any]:
    """Read the contents of a file from the agent's workspace."""
    resp = await core_client.client.post(
        "/v1/skills/file-read/read",
        json={"agent_id": agent_id, "path": path},
        headers=core_client._get_headers(),
    )
    if resp.status_code == 404:
        raise WorkspaceNotFoundError(f"File not found: {path}")
    if resp.status_code == 403:
        raise WorkspacePathError(f"Path traversal blocked: {path}")
    if resp.status_code == 400:
        raise WorkspacePathError(f"Invalid path: {path}")
    resp.raise_for_status()
    return resp.json()


async def file_write(agent_id: str, path: str, content: str, core_client: CoreClient) -> dict[str, Any]:
    """Write content to a file in the agent's workspace."""
    resp = await core_client.client.post(
        "/v1/skills/file-write/write",
        json={"agent_id": agent_id, "path": path, "content": content},
        headers=core_client._get_headers(),
    )
    if resp.status_code == 404:
        raise WorkspaceNotFoundError(f"Parent directory not found: {path}")
    if resp.status_code == 403:
        raise WorkspacePathError(f"Path traversal blocked: {path}")
    if resp.status_code == 413:
        raise WorkspaceQuotaError(f"File too large or quota exceeded: {path}")
    if resp.status_code == 400:
        raise WorkspacePathError(f"Invalid path: {path}")
    resp.raise_for_status()
    return resp.json()


async def file_list(agent_id: str, path: str, core_client: CoreClient) -> dict[str, Any]:
    """List directory entries in the agent's workspace."""
    resp = await core_client.client.post(
        "/v1/skills/file-list/list",
        json={"agent_id": agent_id, "path": path},
        headers=core_client._get_headers(),
    )
    if resp.status_code == 404:
        raise WorkspaceNotFoundError(f"Directory not found: {path}")
    if resp.status_code == 403:
        raise WorkspacePathError(f"Path traversal blocked: {path}")
    if resp.status_code == 400:
        raise WorkspacePathError(f"Invalid path: {path}")
    resp.raise_for_status()
    return resp.json()


async def file_delete(agent_id: str, path: str, core_client: CoreClient) -> dict[str, Any]:
    """Delete a file from the agent's workspace."""
    resp = await core_client.client.post(
        "/v1/skills/file-delete/delete",
        json={"agent_id": agent_id, "path": path},
        headers=core_client._get_headers(),
    )
    if resp.status_code == 404:
        raise WorkspaceNotFoundError(f"File not found: {path}")
    if resp.status_code == 403:
        detail = ""
        try:
            detail = resp.json().get("detail", "")
        except Exception:
            pass
        if "directory" in detail.lower():
            raise WorkspacePermissionError(f"Cannot delete directory: {path}")
        raise WorkspacePathError(f"Path traversal blocked: {path}")
    if resp.status_code == 400:
        raise WorkspacePathError(f"Invalid path: {path}")
    resp.raise_for_status()
    return resp.json()


# LiteLLM-compatible tool definitions
FILE_READ_DEF = {
    "type": "function",
    "function": {
        "name": "file_read",
        "description": _get_tool_desc("file_read", "Read the contents of a file from the agent's workspace."),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file within the workspace",
                }
            },
            "required": ["path"],
        },
    },
}

FILE_WRITE_DEF = {
    "type": "function",
    "function": {
        "name": "file_write",
        "description": _get_tool_desc("file_write", "Write content to a file in the agent's workspace. Creates parent directories if needed."),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file within the workspace",
                },
                "content": {
                    "type": "string",
                    "description": "Text content to write to the file",
                },
            },
            "required": ["path", "content"],
        },
    },
}

FILE_LIST_DEF = {
    "type": "function",
    "function": {
        "name": "file_list",
        "description": _get_tool_desc("file_list", "List files and directories in a path within the agent's workspace."),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the directory within the workspace (defaults to root if omitted)",
                }
            },
            "required": [],
        },
    },
}

FILE_DELETE_DEF = {
    "type": "function",
    "function": {
        "name": "file_delete",
        "description": _get_tool_desc("file_delete", "Delete a file from the agent's workspace. Directories cannot be deleted with this tool."),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file within the workspace",
                }
            },
            "required": ["path"],
        },
    },
}
