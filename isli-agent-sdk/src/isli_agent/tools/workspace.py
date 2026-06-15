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


async def file_read(
    agent_id: str,
    path: str,
    core_client: CoreClient,
    max_chars: int = 16000,
    line_start: int = 1,
    line_end: int | None = None
) -> dict[str, Any]:
    """Read the contents of a file from the agent's workspace."""
    resp = await core_client.client.post(
        "/v1/skills/file-read/read",
        json={
            "agent_id": agent_id,
            "path": path,
            "scope": "agent",
            "scope_id": agent_id,
            "max_chars": max_chars,
            "line_start": line_start,
            "line_end": line_end,
        },
        headers=core_client._get_headers(),
    )
    if resp.status_code == 404:
        raise WorkspaceNotFoundError(f"File not found: {path}")
    if resp.status_code == 403:
        raise WorkspacePathError(f"Path traversal blocked or access denied: {path}")
    if resp.status_code == 400:
        raise WorkspacePathError(f"Invalid path: {path}")
    resp.raise_for_status()
    return resp.json()


async def file_write(agent_id: str, path: str, content: str, core_client: CoreClient) -> dict[str, Any]:
    """Write content to a file in the agent's workspace."""
    resp = await core_client.client.post(
        "/v1/skills/file-write/write",
        json={"agent_id": agent_id, "path": path, "content": content, "scope": "agent", "scope_id": agent_id},
        headers=core_client._get_headers(),
    )
    if resp.status_code == 404:
        raise WorkspaceNotFoundError(f"Parent directory not found: {path}")
    if resp.status_code == 403:
        raise WorkspacePathError(f"Path traversal blocked or access denied: {path}")
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
        json={"agent_id": agent_id, "path": path, "scope": "agent", "scope_id": agent_id},
        headers=core_client._get_headers(),
    )
    if resp.status_code == 404:
        raise WorkspaceNotFoundError(f"Directory not found: {path}")
    if resp.status_code == 403:
        raise WorkspacePathError(f"Path traversal blocked or access denied: {path}")
    if resp.status_code == 400:
        raise WorkspacePathError(f"Invalid path: {path}")
    resp.raise_for_status()
    return resp.json()


async def file_delete(agent_id: str, path: str, core_client: CoreClient) -> dict[str, Any]:
    """Delete a file from the agent's workspace."""
    resp = await core_client.client.post(
        "/v1/skills/file-delete/delete",
        json={"agent_id": agent_id, "path": path, "scope": "agent", "scope_id": agent_id},
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
        raise WorkspacePathError(f"Path traversal blocked or access denied: {path}")
    if resp.status_code == 400:
        raise WorkspacePathError(f"Invalid path: {path}")
    resp.raise_for_status()
    return resp.json()


async def attach_to_task(agent_id: str, file_path: str, task_id: str, core_client: CoreClient) -> dict[str, Any]:
    """Attach a file from the local workspace to a specific task."""
    resp = await core_client.client.post(
        f"/v1/tasks/{task_id}/attachments/attach",
        json={"agent_id": agent_id, "source_path": file_path, "target_path": file_path},
        headers=core_client._get_headers(),
    )
    resp.raise_for_status()
    return resp.json()


async def pull_task_attachment(agent_id: str, task_id: str, file_path: str, core_client: CoreClient) -> dict[str, Any]:
    """Pull an attachment from a task into the local workspace."""
    resp = await core_client.client.post(
        f"/v1/tasks/{task_id}/attachments/pull",
        json={"agent_id": agent_id, "source_path": file_path, "target_path": file_path},
        headers=core_client._get_headers(),
    )
    resp.raise_for_status()
    return resp.json()


async def promote_output(agent_id: str, task_id: str, file_path: str, workspace_id: str, core_client: CoreClient) -> dict[str, Any]:
    """Promote a file from a task workspace to a shared workspace."""
    resp = await core_client.client.post(
        f"/v1/shared-workspaces/{workspace_id}/promote",
        json={
            "agent_id": agent_id,
            "source_scope": "attachment",
            "source_scope_id": task_id,
            "source_path": file_path,
            "target_path": file_path,
            "delete_source": False
        },
        headers=core_client._get_headers(),
    )
    resp.raise_for_status()
    return resp.json()


async def shared_promote_file_workspace(agent_id: str, workspace_id: str, source_path: str, target_path: str, core_client: CoreClient) -> dict[str, Any]:
    """Promote a file from the agent's own workspace into a shared workspace."""
    resp = await core_client.client.post(
        "/v1/skills/shared-promote-file-workspace/promote",
        json={
            "agent_id": agent_id,
            "workspace_id": workspace_id,
            "source_path": source_path,
            "target_path": target_path,
        },
        headers=core_client._get_headers(),
    )
    if resp.status_code == 404:
        raise WorkspaceNotFoundError(f"File or workspace not found: {source_path}")
    if resp.status_code == 403:
        raise WorkspacePathError(f"Access denied to shared workspace: {workspace_id}")
    if resp.status_code == 400:
        raise WorkspacePathError(f"Invalid path or workspace: {source_path}")
    resp.raise_for_status()
    return resp.json()


async def shared_file_read(agent_id: str, workspace_id: str, path: str, core_client: CoreClient, max_chars: int = 16000, line_start: int = 1, line_end: int | None = None) -> dict[str, Any]:
    """Read a file from a shared workspace."""
    resp = await core_client.client.post(
        "/v1/skills/shared-file-read/read",
        json={
            "agent_id": agent_id,
            "path": path,
            "scope": "shared",
            "scope_id": workspace_id,
            "max_chars": max_chars,
            "line_start": line_start,
            "line_end": line_end,
        },
        headers=core_client._get_headers(),
    )
    if resp.status_code == 404:
        raise WorkspaceNotFoundError(f"File not found: {path}")
    if resp.status_code == 403:
        raise WorkspacePathError(f"Access denied or path traversal blocked: {path}")
    if resp.status_code == 400:
        raise WorkspacePathError(f"Invalid path: {path}")
    resp.raise_for_status()
    return resp.json()


async def shared_file_write(agent_id: str, workspace_id: str, path: str, content: str, core_client: CoreClient) -> dict[str, Any]:
    """Write content to a file in a shared workspace."""
    resp = await core_client.client.post(
        "/v1/skills/shared-file-write/write",
        json={"agent_id": agent_id, "path": path, "content": content, "scope": "shared", "scope_id": workspace_id},
        headers=core_client._get_headers(),
    )
    if resp.status_code == 404:
        raise WorkspaceNotFoundError(f"Parent directory not found: {path}")
    if resp.status_code == 403:
        raise WorkspacePathError(f"Access denied or path traversal blocked: {path}")
    if resp.status_code == 413:
        raise WorkspaceQuotaError(f"File too large or quota exceeded: {path}")
    if resp.status_code == 400:
        raise WorkspacePathError(f"Invalid path: {path}")
    resp.raise_for_status()
    return resp.json()


async def shared_file_list(agent_id: str, workspace_id: str, path: str, core_client: CoreClient) -> dict[str, Any]:
    """List directory entries in a shared workspace."""
    resp = await core_client.client.post(
        "/v1/skills/shared-file-list/list",
        json={"agent_id": agent_id, "path": path, "scope": "shared", "scope_id": workspace_id},
        headers=core_client._get_headers(),
    )
    if resp.status_code == 404:
        raise WorkspaceNotFoundError(f"Directory not found: {path}")
    if resp.status_code == 403:
        raise WorkspacePathError(f"Access denied or path traversal blocked: {path}")
    if resp.status_code == 400:
        raise WorkspacePathError(f"Invalid path: {path}")
    resp.raise_for_status()
    return resp.json()


async def shared_file_delete(agent_id: str, workspace_id: str, path: str, core_client: CoreClient) -> dict[str, Any]:
    """Delete a file from a shared workspace."""
    resp = await core_client.client.post(
        "/v1/skills/shared-file-delete/delete",
        json={"agent_id": agent_id, "path": path, "scope": "shared", "scope_id": workspace_id},
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
        raise WorkspacePathError(f"Access denied or path traversal blocked: {path}")
    if resp.status_code == 400:
        raise WorkspacePathError(f"Invalid path: {path}")
    resp.raise_for_status()
    return resp.json()


async def shared_file_move(
    agent_id: str,
    source_workspace_id: str,
    source_path: str,
    target_path: str,
    core_client: CoreClient,
    target_workspace_id: str | None = None,
) -> dict[str, Any]:
    """Move or rename a file within (or between) shared workspaces."""
    resp = await core_client.client.post(
        "/v1/skills/shared-file-move/move",
        json={
            "agent_id": agent_id,
            "source_workspace_id": source_workspace_id,
            "source_path": source_path,
            "target_workspace_id": target_workspace_id,
            "target_path": target_path,
        },
        headers=core_client._get_headers(),
    )
    if resp.status_code == 404:
        raise WorkspaceNotFoundError(f"Source file not found: {source_path}")
    if resp.status_code == 403:
        raise WorkspacePathError(f"Access denied or path traversal blocked")
    if resp.status_code == 413:
        raise WorkspaceQuotaError(f"Target workspace quota exceeded")
    if resp.status_code == 400:
        raise WorkspacePathError(f"Invalid path or workspace: {source_path} -> {target_path}")
    resp.raise_for_status()
    return resp.json()


async def shared_workspace_info(agent_id: str, workspace_id: str, core_client: CoreClient) -> dict[str, Any]:
    """Return metadata for a shared workspace."""
    resp = await core_client.client.post(
        "/v1/skills/shared-workspace-info/info",
        json={"agent_id": agent_id, "workspace_id": workspace_id},
        headers=core_client._get_headers(),
    )
    if resp.status_code == 404:
        raise WorkspaceNotFoundError(f"Shared workspace not found: {workspace_id}")
    if resp.status_code == 403:
        raise WorkspacePathError(f"Access denied to shared workspace: {workspace_id}")
    if resp.status_code == 400:
        raise WorkspacePathError(f"Invalid workspace ID: {workspace_id}")
    resp.raise_for_status()
    return resp.json()


async def shared_workspace_search(
    agent_id: str,
    workspace_id: str,
    query: str,
    core_client: CoreClient,
    path: str = "",
    search_names: bool = True,
    search_content: bool = False,
    case_sensitive: bool = False,
    max_results: int = 50,
) -> dict[str, Any]:
    """Search file names and/or contents across a shared workspace."""
    resp = await core_client.client.post(
        "/v1/skills/shared-workspace-search/search",
        json={
            "agent_id": agent_id,
            "workspace_id": workspace_id,
            "query": query,
            "path": path,
            "search_names": search_names,
            "search_content": search_content,
            "case_sensitive": case_sensitive,
            "max_results": max_results,
        },
        headers=core_client._get_headers(),
    )
    if resp.status_code == 404:
        raise WorkspaceNotFoundError(f"Workspace or path not found: {workspace_id}")
    if resp.status_code == 403:
        raise WorkspacePathError(f"Access denied to shared workspace: {workspace_id}")
    if resp.status_code == 400:
        raise WorkspacePathError(f"Invalid search parameters")
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

ATTACH_TO_TASK_DEF = {
    "type": "function",
    "function": {
        "name": "attach_to_task",
        "description": _get_tool_desc("attach_to_task", "Attach a file from the local workspace to a specific task for another agent to use."),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Relative path to the file to attach"},
                "task_id": {"type": "string", "description": "ID of the task to attach the file to"}
            },
            "required": ["file_path", "task_id"],
        },
    },
}

PULL_TASK_ATTACHMENT_DEF = {
    "type": "function",
    "function": {
        "name": "pull_task_attachment",
        "description": _get_tool_desc("pull_task_attachment", "Pull an attachment from a task into your local workspace. Records source metadata."),
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "ID of the task to pull the attachment from"},
                "file_path": {"type": "string", "description": "Relative path of the attachment on the task"}
            },
            "required": ["task_id", "file_path"],
        },
    },
}

PROMOTE_OUTPUT_DEF = {
    "type": "function",
    "function": {
        "name": "promote_output",
        "description": _get_tool_desc("promote_output", "Promote a file from a task workspace to a shared project workspace."),
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "ID of the task that produced the file"},
                "file_path": {"type": "string", "description": "Relative path of the file in the task workspace"},
                "workspace_id": {"type": "string", "description": "ID of the target shared workspace"}
            },
            "required": ["task_id", "file_path", "workspace_id"],
        },
    },
}

SHARED_PROMOTE_FILE_WORKSPACE_DEF = {
    "type": "function",
    "function": {
        "name": "shared_promote_file_workspace",
        "description": _get_tool_desc("shared_promote_file_workspace", "Promote a file from your own agent workspace into a shared project workspace."),
        "parameters": {
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string", "description": "ID of the target shared workspace"},
                "source_path": {"type": "string", "description": "Relative path of the file in your agent workspace"},
                "target_path": {"type": "string", "description": "Relative destination path in the shared workspace"},
            },
            "required": ["workspace_id", "source_path", "target_path"],
        },
    },
}

SHARED_FILE_READ_DEF = {
    "type": "function",
    "function": {
        "name": "shared_file_read",
        "description": _get_tool_desc("shared_file_read", "Read a file from a shared project workspace."),
        "parameters": {
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string", "description": "ID of the shared workspace"},
                "path": {"type": "string", "description": "Relative path to the file"}
            },
            "required": ["workspace_id", "path"],
        },
    },
}

SHARED_FILE_WRITE_DEF = {
    "type": "function",
    "function": {
        "name": "shared_file_write",
        "description": _get_tool_desc("shared_file_write", "Write content to a file in a shared project workspace. Operation is atomic."),
        "parameters": {
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string", "description": "ID of the shared workspace"},
                "path": {"type": "string", "description": "Relative path to the file"},
                "content": {"type": "string", "description": "Content to write"}
            },
            "required": ["workspace_id", "path", "content"],
        },
    },
}

SHARED_FILE_LIST_DEF = {
    "type": "function",
    "function": {
        "name": "shared_file_list",
        "description": _get_tool_desc("shared_file_list", "List files in a shared project workspace."),
        "parameters": {
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string", "description": "ID of the shared workspace"},
                "path": {"type": "string", "description": "Relative path to the directory (defaults to root)"}
            },
            "required": ["workspace_id"],
        },
    },
}

SHARED_FILE_DELETE_DEF = {
    "type": "function",
    "function": {
        "name": "shared_file_delete",
        "description": _get_tool_desc("shared_file_delete", "Delete a file from a shared project workspace. Directories cannot be deleted with this tool."),
        "parameters": {
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string", "description": "ID of the shared workspace"},
                "path": {"type": "string", "description": "Relative path to the file"}
            },
            "required": ["workspace_id", "path"],
        },
    },
}

SHARED_FILE_MOVE_DEF = {
    "type": "function",
    "function": {
        "name": "shared_file_move",
        "description": _get_tool_desc("shared_file_move", "Move or rename a file within a shared project workspace, or between two shared workspaces."),
        "parameters": {
            "type": "object",
            "properties": {
                "source_workspace_id": {"type": "string", "description": "ID of the source shared workspace"},
                "source_path": {"type": "string", "description": "Relative path of the source file"},
                "target_workspace_id": {"type": "string", "description": "ID of the target shared workspace (omit for same workspace)"},
                "target_path": {"type": "string", "description": "Relative destination path"},
            },
            "required": ["source_workspace_id", "source_path", "target_path"],
        },
    },
}

SHARED_WORKSPACE_INFO_DEF = {
    "type": "function",
    "function": {
        "name": "shared_workspace_info",
        "description": _get_tool_desc("shared_workspace_info", "Return shared workspace metadata: name, members, root path, and quota."),
        "parameters": {
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string", "description": "ID of the shared workspace"},
            },
            "required": ["workspace_id"],
        },
    },
}

SHARED_WORKSPACE_SEARCH_DEF = {
    "type": "function",
    "function": {
        "name": "shared_workspace_search",
        "description": _get_tool_desc("shared_workspace_search", "Search file names and/or contents across a shared project workspace."),
        "parameters": {
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string", "description": "ID of the shared workspace"},
                "query": {"type": "string", "description": "Search query string"},
                "path": {"type": "string", "description": "Relative subdirectory to search under (defaults to root)"},
                "search_names": {"type": "boolean", "description": "Search file names (default true)"},
                "search_content": {"type": "boolean", "description": "Search file contents (default false)"},
                "case_sensitive": {"type": "boolean", "description": "Case-sensitive matching (default false)"},
                "max_results": {"type": "integer", "description": "Maximum number of results (default 50)"},
            },
            "required": ["workspace_id", "query"],
        },
    },
}
