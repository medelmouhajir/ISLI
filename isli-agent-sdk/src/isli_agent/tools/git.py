from typing import Any

from isli_agent.client import CoreClient


def _get_tool_desc(name: str, default: str) -> str:
    try:
        from isli_agent.prompts_loader import get_prompts
        return get_prompts()["agent"]["tool_descriptions"].get(name, default)
    except Exception:
        return default


class GitNotRepoError(Exception):
    """Raised when a path is not a valid git repository."""


class GitAuthError(Exception):
    """Raised on authentication failure with the git remote."""


class GitConflictError(Exception):
    """Raised when a git merge or pull encounters conflicts."""


class GitRemoteError(Exception):
    """Raised on network or remote-related git failures."""


class GitInvalidOperationError(Exception):
    """Raised when the requested git operation is invalid."""


async def git_clone(
    agent_id: str,
    path: str,
    url: str,
    core_client: CoreClient,
    branch: str | None = None,
) -> dict[str, Any]:
    """Clone a remote git repository into the agent's workspace."""
    payload: dict[str, Any] = {
        "agent_id": agent_id,
        "path": path,
        "url": url,
    }
    if branch:
        payload["branch"] = branch
    resp = await core_client.client.post(
        "/v1/skills/git-clone/clone",
        json=payload,
        headers=core_client._get_headers(),
    )
    if resp.status_code == 400:
        raise GitInvalidOperationError(f"Invalid clone operation: {resp.json().get('detail', '')}")
    if resp.status_code == 403:
        raise GitAuthError(f"Authentication failed: {resp.json().get('detail', '')}")
    if resp.status_code == 502:
        raise GitRemoteError(f"Remote error: {resp.json().get('detail', '')}")
    resp.raise_for_status()
    return resp.json()


async def git_status(
    agent_id: str,
    path: str,
    core_client: CoreClient,
) -> dict[str, Any]:
    """Show the working tree status of a git repository."""
    resp = await core_client.client.post(
        "/v1/skills/git-status/status",
        json={"agent_id": agent_id, "path": path},
        headers=core_client._get_headers(),
    )
    if resp.status_code == 404:
        raise GitNotRepoError(f"Not a git repository: {path}")
    resp.raise_for_status()
    return resp.json()


async def git_commit(
    agent_id: str,
    path: str,
    message: str,
    core_client: CoreClient,
    files: list[str] | None = None,
) -> dict[str, Any]:
    """Stage files and commit changes in a git repository."""
    payload: dict[str, Any] = {
        "agent_id": agent_id,
        "path": path,
        "message": message,
    }
    if files:
        payload["files"] = files
    resp = await core_client.client.post(
        "/v1/skills/git-commit/commit",
        json=payload,
        headers=core_client._get_headers(),
    )
    if resp.status_code == 404:
        raise GitNotRepoError(f"Not a git repository: {path}")
    if resp.status_code == 400:
        raise GitInvalidOperationError(f"Invalid commit operation: {resp.json().get('detail', '')}")
    resp.raise_for_status()
    return resp.json()


async def git_push(
    agent_id: str,
    path: str,
    core_client: CoreClient,
    remote: str = "origin",
    branch: str | None = None,
) -> dict[str, Any]:
    """Push the current or specified branch to a remote repository."""
    payload: dict[str, Any] = {
        "agent_id": agent_id,
        "path": path,
        "remote": remote,
    }
    if branch:
        payload["branch"] = branch
    resp = await core_client.client.post(
        "/v1/skills/git-push/push",
        json=payload,
        headers=core_client._get_headers(),
    )
    if resp.status_code == 404:
        raise GitNotRepoError(f"Not a git repository: {path}")
    if resp.status_code == 403:
        raise GitAuthError(f"Authentication failed: {resp.json().get('detail', '')}")
    if resp.status_code == 502:
        raise GitRemoteError(f"Remote error: {resp.json().get('detail', '')}")
    resp.raise_for_status()
    return resp.json()


async def git_pull(
    agent_id: str,
    path: str,
    core_client: CoreClient,
    remote: str = "origin",
    branch: str | None = None,
) -> dict[str, Any]:
    """Pull changes from a remote repository into the current branch."""
    payload: dict[str, Any] = {
        "agent_id": agent_id,
        "path": path,
        "remote": remote,
    }
    if branch:
        payload["branch"] = branch
    resp = await core_client.client.post(
        "/v1/skills/git-pull/pull",
        json=payload,
        headers=core_client._get_headers(),
    )
    if resp.status_code == 404:
        raise GitNotRepoError(f"Not a git repository: {path}")
    if resp.status_code == 409:
        raise GitConflictError(f"Merge conflict: {resp.json().get('detail', '')}")
    if resp.status_code == 403:
        raise GitAuthError(f"Authentication failed: {resp.json().get('detail', '')}")
    if resp.status_code == 502:
        raise GitRemoteError(f"Remote error: {resp.json().get('detail', '')}")
    resp.raise_for_status()
    return resp.json()


async def git_branch_list(
    agent_id: str,
    path: str,
    core_client: CoreClient,
) -> dict[str, Any]:
    """List all branches in a git repository."""
    resp = await core_client.client.post(
        "/v1/skills/git-branch-list/list",
        json={"agent_id": agent_id, "path": path},
        headers=core_client._get_headers(),
    )
    if resp.status_code == 404:
        raise GitNotRepoError(f"Not a git repository: {path}")
    resp.raise_for_status()
    return resp.json()


async def git_branch_create(
    agent_id: str,
    path: str,
    branch_name: str,
    core_client: CoreClient,
    checkout: bool = False,
) -> dict[str, Any]:
    """Create a new branch in a git repository, optionally checking it out."""
    resp = await core_client.client.post(
        "/v1/skills/git-branch-create/create",
        json={
            "agent_id": agent_id,
            "path": path,
            "branch_name": branch_name,
            "checkout": checkout,
        },
        headers=core_client._get_headers(),
    )
    if resp.status_code == 404:
        raise GitNotRepoError(f"Not a git repository: {path}")
    if resp.status_code == 400:
        raise GitInvalidOperationError(f"Invalid branch operation: {resp.json().get('detail', '')}")
    resp.raise_for_status()
    return resp.json()


async def git_checkout(
    agent_id: str,
    path: str,
    branch_name: str,
    core_client: CoreClient,
) -> dict[str, Any]:
    """Checkout (switch to) an existing branch in a git repository."""
    resp = await core_client.client.post(
        "/v1/skills/git-checkout/checkout",
        json={
            "agent_id": agent_id,
            "path": path,
            "branch_name": branch_name,
        },
        headers=core_client._get_headers(),
    )
    if resp.status_code == 404:
        raise GitNotRepoError(f"Not a git repository: {path}")
    if resp.status_code == 400:
        raise GitInvalidOperationError(f"Invalid checkout: {resp.json().get('detail', '')}")
    resp.raise_for_status()
    return resp.json()


async def git_log(
    agent_id: str,
    path: str,
    core_client: CoreClient,
    max_count: int = 10,
) -> dict[str, Any]:
    """Show the commit history of a git repository."""
    resp = await core_client.client.post(
        "/v1/skills/git-log/log",
        json={
            "agent_id": agent_id,
            "path": path,
            "max_count": max_count,
        },
        headers=core_client._get_headers(),
    )
    if resp.status_code == 404:
        raise GitNotRepoError(f"Not a git repository: {path}")
    resp.raise_for_status()
    return resp.json()


# LiteLLM-compatible tool definitions
GIT_CLONE_DEF = {
    "type": "function",
    "function": {
        "name": "git_clone",
        "description": _get_tool_desc("git_clone", "Clone a remote git repository into the agent's workspace."),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path within the workspace where the repository should be cloned",
                },
                "url": {
                    "type": "string",
                    "description": "URL of the remote git repository (https:// or git@)",
                },
                "branch": {
                    "type": "string",
                    "description": "Optional branch to clone (defaults to the repository's default branch)",
                },
            },
            "required": ["path", "url"],
        },
    },
}

GIT_STATUS_DEF = {
    "type": "function",
    "function": {
        "name": "git_status",
        "description": _get_tool_desc(
            "git_status",
            "Show the working tree status of a git repository: modified, staged, and untracked files.",
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the git repository within the workspace",
                },
            },
            "required": ["path"],
        },
    },
}

GIT_COMMIT_DEF = {
    "type": "function",
    "function": {
        "name": "git_commit",
        "description": _get_tool_desc(
            "git_commit",
            "Stage files and commit changes in a git repository with a message. If no files are specified, all changes are staged.",
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the git repository within the workspace",
                },
                "message": {
                    "type": "string",
                    "description": "Commit message",
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of specific files to stage and commit. If omitted, all changes are staged.",
                },
            },
            "required": ["path", "message"],
        },
    },
}

GIT_PUSH_DEF = {
    "type": "function",
    "function": {
        "name": "git_push",
        "description": _get_tool_desc(
            "git_push",
            "Push the current or specified branch to a remote repository.",
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the git repository within the workspace",
                },
                "remote": {
                    "type": "string",
                    "description": "Remote name to push to (default: origin)",
                },
                "branch": {
                    "type": "string",
                    "description": "Optional branch to push. Defaults to the current branch.",
                },
            },
            "required": ["path"],
        },
    },
}

GIT_PULL_DEF = {
    "type": "function",
    "function": {
        "name": "git_pull",
        "description": _get_tool_desc(
            "git_pull",
            "Pull changes from a remote repository into the current branch.",
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the git repository within the workspace",
                },
                "remote": {
                    "type": "string",
                    "description": "Remote name to pull from (default: origin)",
                },
                "branch": {
                    "type": "string",
                    "description": "Optional branch to pull. Defaults to the current branch.",
                },
            },
            "required": ["path"],
        },
    },
}

GIT_BRANCH_LIST_DEF = {
    "type": "function",
    "function": {
        "name": "git_branch_list",
        "description": _get_tool_desc(
            "git_branch_list",
            "List all branches in a git repository, indicating the current branch.",
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the git repository within the workspace",
                },
            },
            "required": ["path"],
        },
    },
}

GIT_BRANCH_CREATE_DEF = {
    "type": "function",
    "function": {
        "name": "git_branch_create",
        "description": _get_tool_desc(
            "git_branch_create",
            "Create a new branch in a git repository, optionally checking it out.",
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the git repository within the workspace",
                },
                "branch_name": {
                    "type": "string",
                    "description": "Name of the new branch to create",
                },
                "checkout": {
                    "type": "boolean",
                    "description": "Whether to checkout the new branch immediately (default: false)",
                },
            },
            "required": ["path", "branch_name"],
        },
    },
}

GIT_CHECKOUT_DEF = {
    "type": "function",
    "function": {
        "name": "git_checkout",
        "description": _get_tool_desc(
            "git_checkout",
            "Checkout (switch to) an existing branch in a git repository.",
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the git repository within the workspace",
                },
                "branch_name": {
                    "type": "string",
                    "description": "Name of the existing branch to checkout",
                },
            },
            "required": ["path", "branch_name"],
        },
    },
}

GIT_LOG_DEF = {
    "type": "function",
    "function": {
        "name": "git_log",
        "description": _get_tool_desc(
            "git_log",
            "Show the commit history of a git repository.",
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the git repository within the workspace",
                },
                "max_count": {
                    "type": "integer",
                    "description": "Maximum number of commits to return (default: 10)",
                },
            },
            "required": ["path"],
        },
    },
}
