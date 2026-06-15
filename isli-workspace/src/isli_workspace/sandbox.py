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


def read_file(
    scope: str,
    scope_id: str,
    base_path: str,
    relative_path: str,
    max_chars: int = 16000,
    line_start: int = 1,
    line_end: int | None = None
) -> dict[str, Any]:
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
        raw_content = path.read_text(encoding="utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        raw_content = path.read_bytes().decode("latin-1")
        encoding = "binary"

    # Line-range Logic
    lines = raw_content.splitlines(keepends=True)
    total_lines = len(lines)
    total_chars = len(raw_content)

    # 1-based indexing for line_start
    start_idx = max(0, line_start - 1)
    if line_end is None:
        end_idx = total_lines
    else:
        end_idx = min(total_lines, line_end)

    sliced_lines = lines[start_idx:end_idx]

    # Truncation Logic
    clamped_max_chars = min(max_chars, 64000)
    current_content = ""
    last_line_included = start_idx
    truncated = False

    for i, line in enumerate(sliced_lines):
        if len(current_content) + len(line) > clamped_max_chars:
            truncated = True
            break
        current_content += line
        last_line_included = start_idx + i + 1

    if truncated:
        notice = f"\n... [truncated: {total_chars} chars total, showing lines {line_start}–{last_line_included} of ~{total_lines}. Use line_start={last_line_included + 1} to continue.]"
        current_content += notice

    return {
        "content": current_content,
        "size_bytes": size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        "encoding": encoding,
        "truncated": truncated,
        "total_lines": total_lines,
        "last_line_included": last_line_included
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


def move_file(
    source_scope: str,
    source_scope_id: str,
    source_base_path: str,
    source_relative_path: str,
    target_scope: str,
    target_scope_id: str,
    target_base_path: str,
    target_relative_path: str,
) -> dict[str, Any]:
    """Move or rename a file. Source and target scopes may be the same or different."""
    src = resolve_path(source_scope, source_scope_id, source_base_path, source_relative_path)
    dst = resolve_path(target_scope, target_scope_id, target_base_path, target_relative_path)

    if not src.exists():
        raise FileNotFoundError(f"File not found: {source_relative_path}")
    if src.is_dir():
        raise IsADirectoryError(f"Cannot move a directory: {source_relative_path}")
    if src.resolve() == dst.resolve():
        raise ValueError("Source and target paths are identical")

    size = src.stat().st_size
    if not check_quota(target_scope, target_scope_id, target_base_path, size):
        raise ValueError("Target workspace quota exceeded")

    dst.parent.mkdir(parents=True, exist_ok=True, mode=0o777)

    # Atomic-ish: copy to a temp file next to the destination, then replace, then remove source.
    fd, temp_path = tempfile.mkstemp(dir=str(dst.parent), prefix=".tmp_move_")
    try:
        with os.fdopen(fd, "wb") as f:
            with open(src, "rb") as sf:
                f.write(sf.read())
        os.replace(temp_path, dst)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise

    try:
        src.unlink()
    except OSError as exc:
        # Best-effort cleanup; the move itself succeeded.
        raise OSError(f"Moved file to {target_relative_path} but failed to remove source: {exc}")

    stat = dst.stat()
    return {
        "status": "moved",
        "path": target_relative_path,
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


def _is_likely_binary(path: Path) -> bool:
    """Guess whether a file is binary by reading the first 1024 bytes."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(1024)
    except OSError:
        return True
    if b"\x00" in chunk:
        return True
    # Use a simple heuristic: if more than 30% of bytes are non-text control chars, treat as binary.
    text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)) - {0x7F})
    if not chunk:
        return False
    non_text = sum(1 for b in chunk if b not in text_chars)
    return non_text / len(chunk) > 0.30


def search_workspace(
    scope: str,
    scope_id: str,
    base_path: str,
    query: str,
    relative_path: str = "",
    search_names: bool = True,
    search_content: bool = False,
    case_sensitive: bool = False,
    max_results: int = 50,
) -> dict[str, Any]:
    """Search file names and/or contents under a workspace scope."""
    root = resolve_path(scope, scope_id, base_path, relative_path)
    if not root.exists():
        raise FileNotFoundError(f"Directory not found: {relative_path}")
    if not root.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {relative_path}")

    if not query:
        raise ValueError("Search query cannot be empty")

    matcher = query if case_sensitive else query.lower()
    matches: list[dict[str, Any]] = []
    total_scanned = 0

    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            if filename.startswith(".") or filename.startswith(".tmp_"):
                continue
            file_path = Path(dirpath) / filename
            try:
                rel = file_path.relative_to(root)
                rel_str = str(rel)
            except ValueError:
                continue

            matched = False
            snippet: str | None = None
            name_to_check = filename if case_sensitive else filename.lower()
            if search_names and matcher in name_to_check:
                matched = True

            if search_content and not matched and file_path.is_file():
                try:
                    if _is_likely_binary(file_path):
                        continue
                    stat = file_path.stat()
                    if stat.st_size > MAX_FILE_SIZE_BYTES:
                        continue
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    content_to_check = content if case_sensitive else content.lower()
                    idx = content_to_check.find(matcher)
                    if idx != -1:
                        matched = True
                        start = max(0, idx - 60)
                        end = min(len(content), idx + len(query) + 60)
                        snippet = content[start:end].replace("\n", " ")
                except (OSError, UnicodeDecodeError):
                    continue

            if matched:
                try:
                    stat = file_path.stat()
                    matches.append({
                        "path": rel_str,
                        "name": filename,
                        "size_bytes": stat.st_size,
                        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                        "snippet": snippet,
                    })
                except FileNotFoundError:
                    continue
                if len(matches) >= max_results:
                    break

        if len(matches) >= max_results:
            break

    return {
        "matches": matches[:max_results],
        "total": len(matches),
        "truncated": len(matches) > max_results,
    }


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

