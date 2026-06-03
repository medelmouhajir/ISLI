"""Package manager operations for ISLI Workspace.

Provides pip install and list capabilities scoped to a workspace sandbox.
Packages are installed with ``--target`` so they persist in the workspace
volume and survive container restarts.
"""

import re
import subprocess
from pathlib import Path
from typing import Any

from .sandbox import _workspace_root, check_quota


class PackageInstallError(Exception):
    """Raised when ``pip install`` fails for a non-validation reason."""


class PackageInvalidError(Exception):
    """Raised when the requested package list contains forbidden flags or invalid names."""


class PackageTimeoutError(Exception):
    """Raised when ``pip install`` exceeds the allowed execution time."""


# pip flags that could redirect to a malicious index or read arbitrary files
_FORBIDDEN_FLAGS = {
    "--index-url",
    "--extra-index-url",
    "--find-links",
    "--no-index",
    "--trusted-host",
    "--requirement",
    "-r",
    "-f",
    "-i",
    "--index",
}

# Rough PEP 508 package name validation (alphanumeric, hyphens, underscores, dots)
_PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9._\-]+$")

# Maximum time to wait for a pip install
_INSTALL_TIMEOUT_SECONDS = 120


def _validate_packages(packages: list[str]) -> None:
    """Validate package specifiers for security.

    Blocks:
      * Forbidden pip CLI flags
      * file:// URLs
      * Shell metacharacters
      * Invalid package name characters
    """
    if not packages:
        raise PackageInvalidError("No packages specified.")

    for spec in packages:
        spec_stripped = spec.strip()
        if not spec_stripped:
            raise PackageInvalidError("Empty package specifier.")

        # Block file:// URLs entirely
        if spec_stripped.startswith("file://"):
            raise PackageInvalidError(f"file:// URLs are not permitted: {spec_stripped}")

        # Block forbidden flags anywhere in the specifier
        for flag in _FORBIDDEN_FLAGS:
            if flag in spec_stripped:
                raise PackageInvalidError(
                    f"Forbidden pip flag '{flag}' detected in specifier: {spec_stripped}"
                )

        # Extract the package name portion (ignore extras and version specifiers for validation)
        # e.g. "requests[security]>=2.0" -> "requests"
        name_match = re.match(r"^([A-Za-z0-9._\-]+)", spec_stripped)
        if not name_match:
            raise PackageInvalidError(
                f"Invalid package name in specifier: {spec_stripped}"
            )
        name = name_match.group(1)
        if not _PACKAGE_NAME_RE.match(name):
            raise PackageInvalidError(
                f"Invalid characters in package name: {name}"
            )


def _get_pip_target(scope: str, scope_id: str, base_path: str) -> Path:
    """Return the ``--target`` directory for pip installations."""
    root = _workspace_root(scope, scope_id, base_path)
    target = root / ".pip-packages"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _run_pip(
    *args: str,
    timeout: int = _INSTALL_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    """Run pip as a subprocess and return the completed process."""
    cmd = ["python", "-m", "pip", *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


async def pip_install(
    scope: str,
    scope_id: str,
    base_path: str,
    packages: list[str],
    upgrade: bool = False,
) -> dict[str, Any]:
    """Install packages into the workspace-scoped pip target directory.

    Uses ``pip install --target`` so packages persist in the workspace volume.
    Respects workspace quota.
    """
    _validate_packages(packages)

    target = _get_pip_target(scope, scope_id, base_path)

    # Rough size check: we can't know download size ahead of time, but we can
    # check current workspace usage. If already at 95 % quota, refuse.
    if not check_quota(scope, scope_id, base_path, additional_bytes=0):
        raise PackageInstallError("Workspace quota already exceeded.")

    cmd_args = [
        "install",
        "--target", str(target),
        "--disable-pip-version-check",
        "--no-cache-dir",
        "--no-input",
    ]
    if upgrade:
        cmd_args.append("--upgrade")
    cmd_args.extend(packages)

    try:
        result = _run_pip(*cmd_args)
    except subprocess.TimeoutExpired as exc:
        raise PackageTimeoutError(
            f"pip install timed out after {_INSTALL_TIMEOUT_SECONDS}s"
        ) from exc

    if result.returncode != 0:
        stderr = result.stderr.strip() if result.stderr else ""
        stdout = result.stdout.strip() if result.stdout else ""
        combined = f"{stdout}\n{stderr}".strip()
        raise PackageInstallError(
            f"pip install failed (exit {result.returncode}): {combined[:500]}"
        )

    # Parse installed lines from stdout for the response
    installed: list[str] = []
    warnings: list[str] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("Successfully installed "):
            installed = stripped.replace("Successfully installed ", "").split()
        elif stripped.startswith("WARNING:"):
            warnings.append(stripped)

    return {
        "status": "installed",
        "packages": packages,
        "target": str(target),
        "installed": installed,
        "warnings": warnings,
    }


async def pip_list(
    scope: str,
    scope_id: str,
    base_path: str,
) -> dict[str, Any]:
    """List packages installed in the workspace-scoped pip target directory."""
    target = _get_pip_target(scope, scope_id, base_path)

    if not any(target.iterdir()):
        return {"status": "ok", "packages": []}

    result = _run_pip(
        "list",
        "--path", str(target),
        "--format=json",
        timeout=30,
    )

    if result.returncode != 0:
        stderr = result.stderr.strip() if result.stderr else ""
        raise PackageInstallError(f"pip list failed: {stderr[:500]}")

    import json

    try:
        raw_packages = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise PackageInstallError("pip list returned invalid JSON")

    packages = [
        {"name": p["name"], "version": p["version"]}
        for p in raw_packages
    ]

    return {"status": "ok", "packages": packages}
