import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
MAX_WORKSPACE_SIZE_BYTES = 100 * 1024 * 1024

SCOPE_PREFIXES = {
    "agent": "agents/{scope_id}",
    "attachment": "_attachments/{scope_id}",
    "shared": "_shared/{scope_id}",
}


def _workspace_root(scope: str, scope_id: str, base_path: str) -> Path:
    prefix_template = SCOPE_PREFIXES.get(scope, "agents/{scope_id}")
    prefix = prefix_template.format(scope_id=scope_id)
    return Path(base_path) / prefix


def _ensure_within_workspace(scope: str, scope_id: str, base_path: str, target: Path) -> None:
    root = _workspace_root(scope, scope_id, base_path).resolve()
    resolved = target.resolve()
    try:
        if not resolved.is_relative_to(root):
            raise PermissionError(f"Path traversal blocked: {resolved}")
    except AttributeError:
        # Fallback for Python < 3.9
        if not str(resolved).startswith(str(root)):
            raise PermissionError(f"Path traversal blocked: {resolved}")


def _get_workspace_size(scope: str, scope_id: str, base_path: str) -> int:
    root = _workspace_root(scope, scope_id, base_path)
    if not root.exists():
        return 0
    total = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for f in filenames:
            fp = Path(dirpath) / f
            try:
                total += fp.stat().st_size
            except FileNotFoundError:
                continue
    return total


def resolve_path(scope: str, scope_id: str, base_path: str, relative_path: str) -> Path:
    root = _workspace_root(scope, scope_id, base_path)
    # Ensure the root exists before resolving against it
    root.mkdir(parents=True, exist_ok=True, mode=0o777)
    target = (root / (relative_path or ".")).resolve()
    _ensure_within_workspace(scope, scope_id, base_path, target)
    return target


def check_quota(scope: str, scope_id: str, base_path: str, additional_bytes: int, max_bytes: int | None = None) -> bool:
    current = _get_workspace_size(scope, scope_id, base_path)
    limit = max_bytes if max_bytes is not None else MAX_WORKSPACE_SIZE_BYTES
    return (current + additional_bytes) <= limit


def read_file(scope: str, scope_id: str, base_path: str, relative_path: str) -> dict[str, Any]:
    path = resolve_path(scope, scope_id, base_path, relative_path)
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


def write_file(scope: str, scope_id: str, base_path: str, relative_path: str, content: str, max_bytes: int | None = None) -> dict[str, Any]:
    path = resolve_path(scope, scope_id, base_path, relative_path)
    encoded_content = content.encode("utf-8")
    size = len(encoded_content)
    if size > MAX_FILE_SIZE_BYTES:
        raise ValueError(f"Content exceeds max file size: {size} bytes")
    if not check_quota(scope, scope_id, base_path, size, max_bytes):
        raise ValueError("Workspace quota exceeded")
    
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o777)
    
    # Atomic write using a temporary file and rename
    fd, temp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_")
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(encoded_content)
        os.replace(temp_path, path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise

    stat = path.stat()
    return {
        "status": "written",
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


def write_file_bytes(scope: str, scope_id: str, base_path: str, relative_path: str, content: bytes, max_bytes: int | None = None) -> dict[str, Any]:
    path = resolve_path(scope, scope_id, base_path, relative_path)
    size = len(content)
    if size > MAX_FILE_SIZE_BYTES:
        raise ValueError(f"Content exceeds max file size: {size} bytes")
    if not check_quota(scope, scope_id, base_path, size, max_bytes):
        raise ValueError("Workspace quota exceeded")
    
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o777)
    
    # Atomic write using a temporary file and rename
    fd, temp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_")
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(content)
        os.replace(temp_path, path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise

    stat = path.stat()
    return {
        "status": "written",
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


def create_dir(scope: str, scope_id: str, base_path: str, relative_path: str) -> dict[str, Any]:
    path = resolve_path(scope, scope_id, base_path, relative_path)
    path.mkdir(parents=True, exist_ok=True, mode=0o777)
    return {
        "status": "created",
        "path": relative_path,
    }


def list_dir(scope: str, scope_id: str, base_path: str, relative_path: str = "") -> dict[str, Any]:
    path = resolve_path(scope, scope_id, base_path, relative_path)
    if not path.exists():
        raise FileNotFoundError(f"Directory not found: {relative_path}")
    if not path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {relative_path}")
    entries = []
    for entry in path.iterdir():
        if entry.name.startswith(".tmp_"):
            continue
        try:
            stat = entry.stat()
            entries.append({
                "name": entry.name,
                "type": "directory" if entry.is_dir() else "file",
                "size_bytes": stat.st_size if entry.is_file() else 0,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            })
        except FileNotFoundError:
            continue
    return {"entries": sorted(entries, key=lambda e: (e["type"] != "directory", e["name"]))}


def delete_file(scope: str, scope_id: str, base_path: str, relative_path: str) -> dict[str, Any]:
    path = resolve_path(scope, scope_id, base_path, relative_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {relative_path}")
    
    if path.is_dir():
        shutil.rmtree(path)
        return {"status": "deleted", "path": relative_path, "type": "directory"}
    else:
        size = path.stat().st_size
        path.unlink()
        return {"status": "deleted", "path": relative_path, "size_bytes": size, "type": "file"}

