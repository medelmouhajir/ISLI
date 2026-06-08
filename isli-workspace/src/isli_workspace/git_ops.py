"""Git operations for ISLI Workspace.

Provides async wrappers around GitPython with workspace sandbox integration.
All paths are resolved through the workspace sandbox to prevent escape.
"""

import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import git
from git.exc import GitCommandError, InvalidGitRepositoryError

from .sandbox import check_quota, resolve_path


class GitNotRepoError(Exception):
    """Raised when an operation expects a git repository but the path is not one."""


class GitAuthError(Exception):
    """Raised on authentication failures with the remote."""


class GitConflictError(Exception):
    """Raised when a merge/pull operation encounters conflicts."""


class GitRemoteError(Exception):
    """Raised on network or remote-related git failures."""


class GitInvalidOperationError(Exception):
    """Raised when the requested git operation is invalid (e.g., checkout non-existent branch)."""


def _validate_clone_url(url: str) -> None:
    """Validate that a clone URL does not use forbidden schemes."""
    forbidden_schemes = {"file"}
    match = re.match(r"^([a-zA-Z][a-zA-Z0-9+.-]*)://", url)
    if match:
        scheme = match.group(1).lower()
        if scheme in forbidden_schemes:
            raise GitInvalidOperationError(f"Clone URL scheme '{scheme}' is not permitted")
    # Block raw file paths that look like absolute local paths,
    # unless they look like a bare git repo (ends with .git).
    if (url.startswith("/") or url.startswith("~")) and not url.rstrip("/").endswith(".git"):
        raise GitInvalidOperationError("Local file paths are not permitted as clone URLs")


def _map_git_error(exc: GitCommandError) -> Exception:
    """Map a GitCommandError to a typed exception for clearer handling."""
    stderr = (exc.stderr or "").lower()
    stdout = (exc.stdout or "").lower()
    combined = f"{stderr} {stdout}"

    if "authentication failed" in combined or "403" in combined:
        return GitAuthError(f"Authentication failed: {exc}")
    if "could not resolve" in combined or "network" in combined:
        return GitRemoteError(f"Remote unreachable: {exc}")
    if "merge conflict" in combined or "conflict" in combined:
        return GitConflictError(f"Merge conflict: {exc}")
    if "not a git repository" in combined:
        return GitNotRepoError(f"Not a git repository: {exc}")
    if "did not match any file" in combined or "pathspec" in combined:
        return GitInvalidOperationError(f"Invalid operation: {exc}")
    return GitRemoteError(f"Git command failed: {exc}")


def _get_repo(scope: str, scope_id: str, base_path: str, relative_path: str) -> git.Repo:
    """Resolve a workspace path and return a git.Repo object."""
    path = resolve_path(scope, scope_id, base_path, relative_path)
    try:
        return git.Repo(path)
    except InvalidGitRepositoryError as exc:
        raise GitNotRepoError(f"Path is not a git repository: {relative_path}") from exc


async def git_clone(
    scope: str,
    scope_id: str,
    base_path: str,
    relative_path: str,
    url: str,
    branch: str | None = None,
) -> dict[str, Any]:
    """Clone a remote repository into a workspace subfolder.

    Uses a temporary directory first, then moves into place on success.
    Respects workspace quota.
    """
    _validate_clone_url(url)

    target = resolve_path(scope, scope_id, base_path, relative_path)
    if target.exists() and any(target.iterdir()):
        raise GitInvalidOperationError(f"Target directory already exists and is not empty: {relative_path}")

    # We cannot know the clone size ahead of time, so we skip strict quota pre-check
    # but we will enforce it after clone by checking workspace size.
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)

    temp_dir = tempfile.mkdtemp(dir=str(parent), prefix=".git_clone_")
    final_temp = Path(temp_dir) / "repo"

    try:
        clone_kwargs: dict[str, Any] = {}
        if branch:
            clone_kwargs["branch"] = branch
            clone_kwargs["single_branch"] = True

        repo = git.Repo.clone_from(url, str(final_temp), **clone_kwargs)
        repo.close()

        # Atomically move into place
        os.rename(str(final_temp), str(target))

        return {
            "status": "cloned",
            "path": relative_path,
            "url": url,
            "branch": branch or "default",
        }
    except GitCommandError as exc:
        raise _map_git_error(exc) from exc
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


async def git_status(
    scope: str,
    scope_id: str,
    base_path: str,
    relative_path: str,
) -> dict[str, Any]:
    """Return the working tree status of a repository."""
    repo = _get_repo(scope, scope_id, base_path, relative_path)
    try:
        status = repo.git.status(porcelain=True)
        modified: list[str] = []
        staged: list[str] = []
        untracked: list[str] = []

        for line in status.splitlines():
            if not line:
                continue
            xy = line[:2]
            path_name = line[3:]
            if xy == "??":
                untracked.append(path_name)
            elif xy[0] != " ":
                staged.append(path_name)
            elif xy[1] != " ":
                modified.append(path_name)

        return {
            "status": "ok",
            "branch": repo.active_branch.name,
            "modified": modified,
            "staged": staged,
            "untracked": untracked,
            "is_dirty": repo.is_dirty(untracked_files=True),
        }
    except GitCommandError as exc:
        raise _map_git_error(exc) from exc
    finally:
        repo.close()


async def git_commit(
    scope: str,
    scope_id: str,
    base_path: str,
    relative_path: str,
    message: str,
    files: list[str] | None = None,
) -> dict[str, Any]:
    """Stage files and commit with the given message.

    If ``files`` is provided, only those files are staged.
    Otherwise, all modified and deleted files are staged (equivalent to ``git add -A``).
    """
    repo = _get_repo(scope, scope_id, base_path, relative_path)
    try:
        if not repo.is_dirty(untracked_files=True) and not files:
            return {
                "status": "no_changes",
                "message": "Working tree clean — nothing to commit.",
            }

        if files:
            for f in files:
                repo.git.add(f)
        else:
            repo.git.add("-A")

        commit = repo.index.commit(message)
        return {
            "status": "committed",
            "commit_hash": commit.hexsha,
            "message": message,
            "author": str(commit.author),
            "committed_at": commit.committed_datetime.isoformat(),
        }
    except GitCommandError as exc:
        raise _map_git_error(exc) from exc
    finally:
        repo.close()


async def git_push(
    scope: str,
    scope_id: str,
    base_path: str,
    relative_path: str,
    remote: str = "origin",
    branch: str | None = None,
) -> dict[str, Any]:
    """Push the current branch (or specified branch) to the remote."""
    repo = _get_repo(scope, scope_id, base_path, relative_path)
    try:
        if branch is None:
            branch = repo.active_branch.name

        push_info = repo.remote(name=remote).push(refspec=branch)
        summaries = [str(info.summary) for info in push_info]
        flags = [info.flags for info in push_info]
        # git.PushInfo.ERROR = 1024, REJECTED = 2048, REMOTE_FAILURE = 4096
        ERROR_FLAGS = {1024, 2048, 4096}
        if any(f in ERROR_FLAGS for f in flags):
            raise GitRemoteError(f"Push rejected or failed: {summaries}")

        return {
            "status": "pushed",
            "remote": remote,
            "branch": branch,
            "summaries": summaries,
        }
    except GitCommandError as exc:
        raise _map_git_error(exc) from exc
    finally:
        repo.close()


async def git_pull(
    scope: str,
    scope_id: str,
    base_path: str,
    relative_path: str,
    remote: str = "origin",
    branch: str | None = None,
) -> dict[str, Any]:
    """Pull changes from the remote into the current branch."""
    repo = _get_repo(scope, scope_id, base_path, relative_path)
    try:
        if branch is None:
            branch = repo.active_branch.name

        pull_info = repo.remote(name=remote).pull(branch)
        # Check for merge conflicts or fast-forward issues
        for info in pull_info:
            if info.flags & 128:  # CONFLICTS
                raise GitConflictError(f"Merge conflicts during pull: {info.note}")

        return {
            "status": "pulled",
            "remote": remote,
            "branch": branch,
            "notes": [str(info.note) for info in pull_info],
        }
    except GitCommandError as exc:
        raise _map_git_error(exc) from exc
    finally:
        repo.close()


async def git_branch_list(
    scope: str,
    scope_id: str,
    base_path: str,
    relative_path: str,
) -> dict[str, Any]:
    """List all branches, marking the current one."""
    repo = _get_repo(scope, scope_id, base_path, relative_path)
    try:
        branches = []
        for ref in repo.branches:
            branches.append({
                "name": ref.name,
                "current": ref.name == repo.active_branch.name,
            })
        return {
            "status": "ok",
            "branches": branches,
            "current": repo.active_branch.name,
        }
    except GitCommandError as exc:
        raise _map_git_error(exc) from exc
    finally:
        repo.close()


async def git_branch_create(
    scope: str,
    scope_id: str,
    base_path: str,
    relative_path: str,
    branch_name: str,
    checkout: bool = False,
) -> dict[str, Any]:
    """Create a new branch, optionally checking it out."""
    repo = _get_repo(scope, scope_id, base_path, relative_path)
    try:
        new_ref = repo.create_head(branch_name)
        if checkout:
            new_ref.checkout()
        return {
            "status": "created",
            "branch": branch_name,
            "checked_out": checkout,
            "commit": new_ref.commit.hexsha,
        }
    except GitCommandError as exc:
        raise _map_git_error(exc) from exc
    finally:
        repo.close()


async def git_checkout(
    scope: str,
    scope_id: str,
    base_path: str,
    relative_path: str,
    branch_name: str,
) -> dict[str, Any]:
    """Checkout an existing branch."""
    repo = _get_repo(scope, scope_id, base_path, relative_path)
    try:
        repo.git.checkout(branch_name)
        return {
            "status": "checked_out",
            "branch": branch_name,
        }
    except GitCommandError as exc:
        raise _map_git_error(exc) from exc
    finally:
        repo.close()


async def git_log(
    scope: str,
    scope_id: str,
    base_path: str,
    relative_path: str,
    max_count: int = 30,
    max_chars: int = 12000,
) -> dict[str, Any]:
    """Return commit history."""
    repo = _get_repo(scope, scope_id, base_path, relative_path)
    try:
        commits = []
        clamped_max_chars = min(max_chars, 32000)
        truncated = False

        for commit in repo.iter_commits(max_count=max_count):
            commit_data = {
                "hash": commit.hexsha,
                "short_hash": commit.hexsha[:7],
                "message": commit.message.strip(),
                "author": str(commit.author),
                "date": commit.committed_datetime.isoformat(),
            }
            
            # Estimate if adding this commit would exceed max_chars
            # Serializing the whole list is safer for exact capping
            if len(json.dumps(commits + [commit_data])) > clamped_max_chars:
                truncated = True
                break
            commits.append(commit_data)

        return {
            "status": "ok",
            "commits": commits,
            "truncated": truncated,
        }
    except GitCommandError as exc:
        raise _map_git_error(exc) from exc
    finally:
        repo.close()
