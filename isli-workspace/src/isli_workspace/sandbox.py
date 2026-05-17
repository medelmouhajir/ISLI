import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
MAX_WORKSPACE_SIZE_BYTES = 100 * 1024 * 1024


def _workspace_root(agent_id: str, base_path: str) -> Path:
    return Path(base_path) / agent_id


def _ensure_within_workspace(agent_id: str, base_path: str, target: Path) -> None:
    root = _workspace_root(agent_id, base_path).resolve()
    resolved = target.resolve()
    if not str(resolved).startswith(str(root)):
        raise PermissionError(f"Path traversal blocked: {resolved}")


def _get_workspace_size(agent_id: str, base_path: str) -> int:
    root = _workspace_root(agent_id, base_path)
    if not root.exists():
        return 0
    total = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for f in filenames:
            fp = Path(dirpath) / f
            total += fp.stat().st_size
    return total


def resolve_path(agent_id: str, base_path: str, relative_path: str) -> Path:
    root = _workspace_root(agent_id, base_path)
    target = (root / relative_path).resolve()
    _ensure_within_workspace(agent_id, base_path, target)
    return target


def check_quota(agent_id: str, base_path: str, additional_bytes: int) -> bool:
    current = _get_workspace_size(agent_id, base_path)
    return (current + additional_bytes) <= MAX_WORKSPACE_SIZE_BYTES


def read_file(agent_id: str, base_path: str, relative_path: str) -> dict[str, Any]:
    path = resolve_path(agent_id, base_path, relative_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {relative_path}")
    if path.is_dir():
        raise IsADirectoryError(f"Path is a directory: {relative_path}")
    stat = path.stat()
    size = stat.st_size
    if size > MAX_FILE_SIZE_BYTES:
        raise OSError(f"File exceeds max size: {size} bytes")
    try:
        content = path.read_text(encoding="utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        content = path.read_bytes().decode("latin-1")
        encoding = "binary"
    return {
        "content": content,
        "size_bytes": size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "encoding": encoding,
    }


def write_file(agent_id: str, base_path: str, relative_path: str, content: str) -> dict[str, Any]:
    path = resolve_path(agent_id, base_path, relative_path)
    size = len(content.encode("utf-8"))
    if size > MAX_FILE_SIZE_BYTES:
        raise ValueError(f"Content exceeds max file size: {size} bytes")
    if not check_quota(agent_id, base_path, size):
        raise ValueError("Workspace quota exceeded")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    stat = path.stat()
    return {
        "status": "written",
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


def list_dir(agent_id: str, base_path: str, relative_path: str = "") -> dict[str, Any]:
    path = resolve_path(agent_id, base_path, relative_path)
    if not path.exists():
        raise FileNotFoundError(f"Directory not found: {relative_path}")
    if not path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {relative_path}")
    entries = []
    for entry in path.iterdir():
        stat = entry.stat()
        entries.append({
            "name": entry.name,
            "type": "directory" if entry.is_dir() else "file",
            "size_bytes": stat.st_size if entry.is_file() else 0,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        })
    return {"entries": sorted(entries, key=lambda e: (e["type"] != "directory", e["name"]))}


def delete_file(agent_id: str, base_path: str, relative_path: str) -> dict[str, Any]:
    path = resolve_path(agent_id, base_path, relative_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {relative_path}")
    if path.is_dir():
        raise IsADirectoryError(f"Cannot delete directory via file delete: {relative_path}")
    size = path.stat().st_size
    path.unlink()
    return {"status": "deleted", "size_bytes": size}
