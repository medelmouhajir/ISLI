import asyncio
import base64
import json
import os
import subprocess
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import httpx
import structlog

from isli_core.auth import create_internal_token, SkillProxyAuth, require_admin_auth
from isli_core.security.content_scanner import ContentScanner
from isli_core.security.policy_engine import PolicyEngine
from isli_core.db import get_db
from isli_core.redis_client import get_redis
from isli_core.file_tokens import create_file_token, consume_file_token
from isli_core.memory.keeper_client import KeeperClient
from isli_core.memory.chroma_client import ChromaMemoryClient
from isli_core.services.skill_manager import skill_manager
from isli_core.config import get_settings
from isli_core.event_manager import EventManager
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

logger = structlog.get_logger()
router = APIRouter(prefix="/skills", tags=["skills"])

class SkillInstallRequest(BaseModel):
    skill_id: str
    git_url: str

# Consolidated upstream URLs — replaces ~25 SKILL_*_URL env vars.
# In Docker Compose: SKILLS_URL, WORKSPACE_URL, AUDIO_URL, KEEPER_URL, CHANNELS_URL.
_SKILLS_URL = os.getenv("SKILLS_URL", "http://localhost:8100")
_WORKSPACE_URL = os.getenv("WORKSPACE_URL", "http://localhost:8300")
_AUDIO_URL = os.getenv("AUDIO_URL", "http://localhost:8400")

SKILL_REGISTRY = {
    # skills microservice
    "web-fetch": _SKILLS_URL,
    "web-search": _SKILLS_URL,
    "summarize": _SKILLS_URL,
    "translate": _SKILLS_URL,
    "shell-exec": _SKILLS_URL,
    "summarize-text": _SKILLS_URL,
    "embed-text": _SKILLS_URL,
    "test-skill": _SKILLS_URL,
    "register-skill": _SKILLS_URL,
    "update-skill": _SKILLS_URL,
    "interactive-debugger": _SKILLS_URL,
    "db-query": _SKILLS_URL,
    "files-documents-manager": _SKILLS_URL,
    # workspace service
    "file-read": _WORKSPACE_URL,
    "file-write": _WORKSPACE_URL,
    "file-list": _WORKSPACE_URL,
    "file-delete": _WORKSPACE_URL,
    "file-search": _WORKSPACE_URL,
    "file-describe": _WORKSPACE_URL,
    "shared-file-read": _WORKSPACE_URL,
    "shared-file-write": _WORKSPACE_URL,
    "shared-file-list": _WORKSPACE_URL,
    "shared-file-delete": _WORKSPACE_URL,
    "shared-file-move": f"{_WORKSPACE_URL}/shared",
    "shared-workspace-search": f"{_WORKSPACE_URL}/shared",
    "git-clone": _WORKSPACE_URL,
    "git-status": _WORKSPACE_URL,
    "git-commit": _WORKSPACE_URL,
    "git-push": _WORKSPACE_URL,
    "git-pull": _WORKSPACE_URL,
    "git-branch-list": _WORKSPACE_URL,
    "git-branch-create": _WORKSPACE_URL,
    "git-checkout": _WORKSPACE_URL,
    "git-log": _WORKSPACE_URL,
    "pip-install": _WORKSPACE_URL,
    "pip-list": _WORKSPACE_URL,
    # audio service
    "speech-to-text": f"{_AUDIO_URL}/stt",
    "text-to-speech": f"{_AUDIO_URL}/tts",
    # browser automation (hosted on skills service)
    "web-browse-navigate": f"{_SKILLS_URL}/browse",
    "web-browse-snapshot": f"{_SKILLS_URL}/browse",
    "web-browse-click": f"{_SKILLS_URL}/browse",
    "web-browse-type": f"{_SKILLS_URL}/browse",
    "web-browse-press": f"{_SKILLS_URL}/browse",
    "web-browse-scroll": f"{_SKILLS_URL}/browse",
    "web-browse-back": f"{_SKILLS_URL}/browse",
    "web-browse-console": f"{_SKILLS_URL}/browse",
    "web-browse-vision": f"{_SKILLS_URL}/browse",
    "web-browse-images": f"{_SKILLS_URL}/browse",
    # inline handlers (executed within Core)
    "get-secret": "inline",
    "shared-promote-file-workspace": "inline",
    "shared-workspace-info": "inline",
    "memory-save": "inline",
    "memory-delete": "inline",
    "memory-search": "inline",
    "send-message": "inline",
    "create-kanban-task": "inline",
    "create-engineering-plan": "inline",
    "ui-components": "inline",
    "notify-user": "inline",
    "list-kanban-tasks": "inline",
    "update-kanban-task": "inline",
}

# Metadata exposed via GET /v1/skills for dynamic skill discovery.
SKILL_METADATA: dict[str, dict[str, Any]] = {
    "web-fetch": {
        "description": "Fetch content from a URL and return structured data.",
        "type": "external",
        "category": "web",
    },
    "summarize": {
        "description": "Summarize long text into a concise summary.",
        "type": "external",
        "category": "content",
    },
    "translate": {
        "description": "Translate text between languages.",
        "type": "external",
        "category": "content",
    },
    "shell-exec": {
        "description": "Execute a shell command safely.",
        "type": "external",
        "category": "system",
    },
    "web-search": {
        "description": "Search the web using local SearXNG instance. For API keys, pass [[secret:SECRET_NAME]].",
        "type": "external",
        "category": "web",
        "secret_fields": ["api_key"],
    },
    "web-browse-navigate": {
        "description": "Navigate a browser to a URL. Creates or reuses a persistent session per agent.",
        "type": "external",
        "category": "web",
    },
    "web-browse-snapshot": {
        "description": "Take an accessibility-tree snapshot of the current page. Returns compact text with @ref IDs for interactive elements.",
        "type": "external",
        "category": "web",
    },
    "web-browse-click": {
        "description": "Click an element by its @ref ID from the last snapshot.",
        "type": "external",
        "category": "web",
    },
    "web-browse-type": {
        "description": "Type text into an input field by its @ref ID.",
        "type": "external",
        "category": "web",
    },
    "web-browse-press": {
        "description": "Press a keyboard key (Enter, Tab, Escape, etc.).",
        "type": "external",
        "category": "web",
    },
    "web-browse-scroll": {
        "description": "Scroll the page up or down.",
        "type": "external",
        "category": "web",
    },
    "web-browse-back": {
        "description": "Navigate back in browser history.",
        "type": "external",
        "category": "web",
    },
    "web-browse-console": {
        "description": "Return browser console logs captured since the last call.",
        "type": "external",
        "category": "web",
    },
    "web-browse-vision": {
        "description": "Take a screenshot of the current page and return it as base64.",
        "type": "external",
        "category": "web",
    },
    "web-browse-images": {
        "description": "List all image elements on the current page with src and alt text.",
        "type": "external",
        "category": "web",
    },
    "files-documents-manager": {
        "description": "Generate documents in PDF, DOCX, or XLSX formats and save them to the workspace.",
        "type": "external",
        "category": "workspace",
    },
    "file-read": {
        "description": "Read a file from the agent workspace.",
        "type": "external",
        "category": "workspace",
    },
    "file-write": {
        "description": "Write or overwrite a file in the agent workspace.",
        "type": "external",
        "category": "workspace",
    },
    "file-list": {
        "description": "List files and directories in the agent workspace.",
        "type": "external",
        "category": "workspace",
    },
    "file-delete": {
        "description": "Delete a file from the agent workspace.",
        "type": "external",
        "category": "workspace",
    },
    "file-search": {
        "description": "Search for a regex or string within a single file in the agent workspace.",
        "type": "external",
        "category": "workspace",
    },
    "file-describe": {
        "description": "Provide structure and stats for a specific file in the agent workspace to aid navigation.",
        "type": "external",
        "category": "workspace",
    },
    "shared-file-read": {
        "description": "Read a file from a shared workspace by workspace_id and path.",
        "type": "external",
        "category": "workspace",
    },
    "shared-file-write": {
        "description": "Write a file into a shared workspace by workspace_id and path.",
        "type": "external",
        "category": "workspace",
    },
    "shared-file-list": {
        "description": "List files and directories inside a shared workspace.",
        "type": "external",
        "category": "workspace",
    },
    "shared-file-delete": {
        "description": "Delete a file from a shared workspace.",
        "type": "external",
        "category": "workspace",
    },
    "shared-file-move": {
        "description": "Move or rename a file within (or between) shared workspaces.",
        "type": "external",
        "category": "workspace",
    },
    "shared-promote-file-workspace": {
        "description": "Promote a file from the agent's own workspace into a shared workspace.",
        "type": "inline",
        "category": "workspace",
    },
    "shared-workspace-info": {
        "description": "Return shared workspace metadata: name, members, root path, and quota.",
        "type": "inline",
        "category": "workspace",
    },
    "shared-workspace-search": {
        "description": "Search file names and/or contents across a shared workspace.",
        "type": "external",
        "category": "workspace",
    },
    "summarize-text": {
        "description": "Summarize text using the Keeper sidecar.",
        "type": "external",
        "category": "content",
    },
    "embed-text": {
        "description": "Generate text embeddings using the Keeper sidecar.",
        "type": "external",
        "category": "content",
    },
    "test-skill": {
        "description": "Dry-run test dynamic skill code in a sandbox.",
        "type": "external",
        "category": "engineering",
    },
    "register-skill": {
        "description": "Register a new dynamic skill after successful testing.",
        "type": "external",
        "category": "engineering",
    },
    "update-skill": {
        "description": "Update metadata of an existing dynamic skill.",
        "type": "external",
        "category": "engineering",
    },
    "interactive-debugger": {
        "description": "Run code in an interactive debugger with breakpoints and variable inspection.",
        "type": "external",
        "category": "engineering",
    },
    "speech-to-text": {
        "description": "Transcribe audio to text using local Whisper STT.",
        "type": "external",
        "category": "audio",
    },
    "text-to-speech": {
        "description": "Synthesize speech from text using local Piper TTS.",
        "type": "external",
        "category": "audio",
    },
    "db-query": {
        "description": "Run a read-only SQL query against the ISLI database. Returns structured tabular results. For database passwords, pass [[secret:SECRET_NAME]].",
        "type": "external",
        "category": "database",
        "secret_fields": ["password", "connection_string"],
    },
    "git-clone": {
        "description": "Clone a remote git repository into the agent's workspace. Supports optional branch selection.",
        "type": "external",
        "category": "git",
    },
    "git-status": {
        "description": "Show the working tree status of a git repository: modified, staged, and untracked files.",
        "type": "external",
        "category": "git",
    },
    "git-commit": {
        "description": "Stage files and commit changes in a git repository with a message.",
        "type": "external",
        "category": "git",
    },
    "git-push": {
        "description": "Push the current or specified branch to a remote repository.",
        "type": "external",
        "category": "git",
    },
    "git-pull": {
        "description": "Pull changes from a remote repository into the current branch.",
        "type": "external",
        "category": "git",
    },
    "git-branch-list": {
        "description": "List all branches in a git repository, indicating the current branch.",
        "type": "external",
        "category": "git",
    },
    "git-branch-create": {
        "description": "Create a new branch in a git repository, optionally checking it out.",
        "type": "external",
        "category": "git",
    },
    "git-checkout": {
        "description": "Checkout (switch to) an existing branch in a git repository.",
        "type": "external",
        "category": "git",
    },
    "git-log": {
        "description": "Show the commit history of a git repository.",
        "type": "external",
        "category": "git",
    },
    "pip-install": {
        "description": "Install Python packages from PyPI into the agent's workspace. Uses pip install --target so packages persist across restarts.",
        "type": "external",
        "category": "workspace",
    },
    "pip-list": {
        "description": "List Python packages installed in the agent's workspace via pip-install.",
        "type": "external",
        "category": "workspace",
    },
    "get-secret": {
        "description": "Retrieve a secret value from the agent's secure vault by name. Used to access API keys, database credentials, or tokens without hardcoding them.",
        "type": "inline",
        "category": "system",
    },
    "memory-save": {
        "description": "Save a fact to the agent's semantic memory.",
        "type": "inline",
        "category": "memory",
    },
    "memory-delete": {
        "description": "Delete a fact from the agent's semantic memory.",
        "type": "inline",
        "category": "memory",
    },
    "memory-search": {
        "description": "Search the agent's semantic memory for relevant facts.",
        "type": "inline",
        "category": "memory",
    },
    "send-message": {
        "description": "Send a message to a user via their channel.",
        "type": "inline",
        "category": "communication",
    },
    "create-kanban-task": {
        "description": "Create a task on the Kanban board, optionally assigned to yourself or another agent. Supports one-off scheduling via scheduled_at (ISO 8601 datetime) or recurring execution via cron_expression (standard 5-field cron). Assigning a task to yourself with a future scheduled_at acts as a self-reminder/wake-up call. scheduled_at and cron_expression are mutually exclusive — set one or neither, not both.",
        "hint": "Create a Kanban task or self-reminder, optionally scheduled or recurring.",
        "type": "inline",
        "category": "kanban",
    },
    "create-engineering-plan": {
        "description": "Generate a structured SE implementation plan (PLAN.md).",
        "type": "inline",
        "category": "engineering",
    },
    "ui-components": {
        "description": "Render interactive UI components (tables, cards, buttons) inline in chat.",
        "type": "inline",
        "category": "system",
    },
    "notify-user": {
        "description": "Send a notification to a user through the unified notification system. Respects user preferences, quiet hours, and rate limits (max 20/hour per user per agent).",
        "type": "inline",
        "category": "communication",
    },
    "list-kanban-tasks": {
        "description": "Query the Kanban board for tasks based on status, assignee, or tags.",
        "type": "inline",
        "category": "kanban",
    },
    "update-kanban-task": {
        "description": "Update an existing Kanban task's status, priority, or append a comment/handoff note.",
        "type": "inline",
        "category": "kanban",
    },
}


def _get_skill_hint(name: str, meta: dict[str, Any]) -> str:
    """Return a compressed hint for skill intent classification.

    Explicit 'hint' field in SKILL_METADATA takes priority.
    Otherwise, truncate description to max 8 words.
    """
    explicit = meta.get("hint")
    if explicit:
        return explicit
    desc = meta.get("description", "")
    words = desc.split()
    if len(words) <= 8:
        return desc
    return " ".join(words[:8]) + "..."


chroma = ChromaMemoryClient()


class SkillRequest(BaseModel):
    action: str
    payload: dict[str, Any]


class SkillMetadataOut(BaseModel):
    name: str
    description: str
    type: str
    category: str = "uncategorized"
    url: str | None = None
    status: str | None = None
    last_probe_status: str | None = None
    last_probe_at: str | None = None
    version: str | None = None
    author: str | None = None
    tools: list[dict[str, Any]] = []
    # Versioning fields
    source_url: str | None = None
    source_ref: str | None = None
    installed_commit_sha: str | None = None
    latest_commit_sha: str | None = None
    latest_version: str | None = None
    update_policy: str = "manual"
    changelog: list[dict[str, Any]] = []
    last_checked_at: str | None = None


class SkillUpdateCheckOut(BaseModel):
    has_update: bool
    current_version: str | None = None
    latest_version: str | None = None
    current_commit: str | None = None
    latest_commit: str | None = None
    changelog: list[dict[str, Any]] = []
    update_policy: str = "manual"
    last_checked_at: str | None = None


class SkillUpdateRequest(BaseModel):
    target_version: str | None = None
    force: bool = False


class SkillRollbackOut(BaseModel):
    skill_id: str
    rolled_back_to_version: str | None = None
    rolled_back_to_commit: str | None = None
    status: str


class SkillPatchRequest(BaseModel):
    update_policy: str | None = None
    source_ref: str | None = None


@router.get("", response_model=list[SkillMetadataOut])
async def list_skills():
    """Return metadata for all registered skills.

    Used by agents at startup for dynamic skill discovery and tool auto-registration.
    """
    skills = []
    # Static skills
    for name, base_url in SKILL_REGISTRY.items():
        meta = SKILL_METADATA.get(name, {})
        skills.append(
            SkillMetadataOut(
                name=name,
                description=meta.get("description", ""),
                type=meta.get("type", "external"),
                category=meta.get("category", "uncategorized"),
                url=base_url if base_url != "inline" else None,
                status="builtin",
            )
        )

    # DB-backed external skills + legacy dynamic skills (unified)
    all_meta = await skill_manager.get_all_metadata()
    for skill_id, meta in all_meta.items():
        skills.append(
            SkillMetadataOut(
                name=skill_id,
                description=meta.get("description", ""),
                type=meta.get("type", "external"),
                category=meta.get("category", "custom"),
                url=None,
                status=meta.get("status"),
                last_probe_status=meta.get("last_probe_status"),
                last_probe_at=meta.get("last_probe_at"),
                version=meta.get("version"),
                author=meta.get("author"),
                tools=meta.get("tools", []),
                source_url=meta.get("source_url"),
                source_ref=meta.get("source_ref"),
                installed_commit_sha=meta.get("installed_commit_sha"),
                latest_commit_sha=meta.get("latest_commit_sha"),
                latest_version=meta.get("latest_version"),
                update_policy=meta.get("update_policy", "manual"),
                changelog=meta.get("changelog", []),
                last_checked_at=meta.get("last_checked_at"),
            )
        )

    return skills


@router.get("/{skill_name}", response_model=SkillMetadataOut)
async def get_skill(skill_name: str):
    """Return metadata for a single skill, including manifest tools."""
    # Check static registry first
    base_url = SKILL_REGISTRY.get(skill_name)
    if base_url:
        meta = SKILL_METADATA.get(skill_name, {})
        return SkillMetadataOut(
            name=skill_name,
            description=meta.get("description", ""),
            type=meta.get("type", "external"),
            category=meta.get("category", "uncategorized"),
            url=base_url if base_url != "inline" else None,
            status="builtin",
        )

    # Check unified registry (legacy dynamic + DB-backed)
    all_meta = await skill_manager.get_all_metadata()
    if skill_name in all_meta:
        meta = all_meta[skill_name]
        return SkillMetadataOut(
            name=skill_name,
            description=meta.get("description", ""),
            type=meta.get("type", "external"),
            category=meta.get("category", "custom"),
            url=None,
            status=meta.get("status"),
            last_probe_status=meta.get("last_probe_status"),
            last_probe_at=meta.get("last_probe_at"),
            version=meta.get("version"),
            author=meta.get("author"),
            tools=meta.get("tools", []),
            source_url=meta.get("source_url"),
            source_ref=meta.get("source_ref"),
            installed_commit_sha=meta.get("installed_commit_sha"),
            latest_commit_sha=meta.get("latest_commit_sha"),
            latest_version=meta.get("latest_version"),
            update_policy=meta.get("update_policy", "manual"),
            changelog=meta.get("changelog", []),
            last_checked_at=meta.get("last_checked_at"),
        )

    raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")


@router.post("/install")
async def install_skill(
    request: SkillInstallRequest,
    admin_key: str = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db),
):
    """Install a skill from a git repository into the DB registry (does not start container)."""
    try:
        skill = await skill_manager.install_from_git(
            skill_id=request.skill_id,
            git_url=request.git_url,
            installed_by="admin",
        )
        return {
            "status": "installed",
            "skill_id": skill.id,
            "name": skill.name,
            "version": skill.version,
            "category": skill.category,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/install-and-enable")
async def install_and_enable_skill(
    request: SkillInstallRequest,
    admin_key: str = Depends(require_admin_auth),
):
    """Install a skill from git and immediately build/start the container."""
    import time
    start_time = time.monotonic()
    try:
        skill = await skill_manager.install_from_git(
            skill_id=request.skill_id,
            git_url=request.git_url,
            installed_by="admin",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    try:
        await skill_manager.enable(request.skill_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(
            status_code=502,
            detail={"error": str(e), "skill_id": request.skill_id, "phase": "enable"},
        ) from e

    # Probe with retry loop (max 60s)
    probe_ok = False
    probe_result: dict[str, Any] = {}
    for attempt in range(20):
        probe_result = await skill_manager.probe(request.skill_id)
        if probe_result.get("ok"):
            probe_ok = True
            break
        await asyncio.sleep(3.0)

    build_time_ms = round((time.monotonic() - start_time) * 1000, 2)

    if not probe_ok:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "Skill container started but health probe failed",
                "skill_id": request.skill_id,
                "probe": probe_result,
                "build_time_ms": build_time_ms,
            },
        )

    # Fetch manifest tools for the broadcast
    manifest = await skill_manager.get_skill_manifest(request.skill_id) or {}
    tools = manifest.get("tools", [])

    # Broadcast event to board and agents
    await EventManager.emit(
        "skill:enabled",
        {
            "skill_id": request.skill_id,
            "skill_name": skill.name,
            "category": skill.category,
            "tools": tools,
        },
    )

    return {
        "status": "active",
        "skill_id": request.skill_id,
        "name": skill.name,
        "version": skill.version,
        "category": skill.category,
        "build_time_ms": build_time_ms,
        "probe_ok": True,
    }


@router.post("/{skill_id}/enable")
async def enable_skill(
    skill_id: str,
    admin_key: str = Depends(require_admin_auth),
):
    """Build and start the skill container."""
    try:
        await skill_manager.enable(skill_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    # Fetch manifest tools for the broadcast
    manifest = await skill_manager.get_skill_manifest(skill_id) or {}
    tools = manifest.get("tools", [])
    meta = await skill_manager.get_all_metadata()
    skill_meta = meta.get(skill_id, {})

    await EventManager.emit(
        "skill:enabled",
        {
            "skill_id": skill_id,
            "skill_name": skill_meta.get("name", skill_id),
            "category": skill_meta.get("category", "custom"),
            "tools": tools,
        },
    )

    return {"status": "enabled", "skill_id": skill_id}


@router.post("/{skill_id}/disable")
async def disable_skill(
    skill_id: str,
    admin_key: str = Depends(require_admin_auth),
):
    """Stop the skill container."""
    try:
        await skill_manager.disable(skill_id)
        return {"status": "disabled", "skill_id": skill_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/{skill_id}")
async def uninstall_skill(
    skill_id: str,
    admin_key: str = Depends(require_admin_auth),
):
    """Remove a skill completely (container, image, DB row, source)."""
    try:
        await skill_manager.uninstall(skill_id)
        return {"status": "uninstalled", "skill_id": skill_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{skill_id}/probe")
async def probe_skill(skill_id: str):
    """Health-check a skill's /health endpoint."""
    result = await skill_manager.probe(skill_id)
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=result)
    return result


@router.post("/{skill_id}/check-update", response_model=SkillUpdateCheckOut)
async def check_update_skill(
    skill_id: str,
    admin_key: str = Depends(require_admin_auth),
):
    """Check remote git repository for a newer version of the skill."""
    try:
        result = await skill_manager.check_update(skill_id)
        return SkillUpdateCheckOut(**result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.post("/{skill_id}/update")
async def update_skill(
    skill_id: str,
    request: SkillUpdateRequest,
    admin_key: str = Depends(require_admin_auth),
):
    """Pull new source, build new image, and perform a blue/green container swap."""
    try:
        skill = await skill_manager.update(skill_id, target_version=request.target_version, force=request.force)
        return {
            "status": "updated",
            "skill_id": skill.id,
            "version": skill.version,
            "previous_version": skill.previous_version,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=409 if "already in progress" in str(e) or "pinned" in str(e) else 502, detail=str(e)) from e


@router.post("/{skill_id}/rollback", response_model=SkillRollbackOut)
async def rollback_skill(
    skill_id: str,
    admin_key: str = Depends(require_admin_auth),
):
    """Rollback a skill to its previous version."""
    try:
        skill = await skill_manager.rollback(skill_id)
        return SkillRollbackOut(
            skill_id=skill.id,
            rolled_back_to_version=skill.version,
            rolled_back_to_commit=skill.installed_commit_sha,
            status=skill.status,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=409 if "already in progress" in str(e) else 502, detail=str(e)) from e


@router.get("/{skill_id}/versions")
async def list_skill_versions(
    skill_id: str,
    admin_key: str = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db),
):
    """List available git tags for a skill."""
    from isli_core.models import SkillRegistry as SkillRegistryModel
    result = await db.execute(select(SkillRegistryModel).where(SkillRegistryModel.id == skill_id))
    skill = result.scalar_one_or_none()
    if not skill or not skill.source_url:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found or has no source_url")
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "ls-remote", "--tags", "--refs", skill.source_url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        if proc.returncode != 0:
            raise RuntimeError(stderr.decode().strip())
        tags = []
        for line in stdout.decode().strip().splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].startswith("refs/tags/"):
                tag = parts[1].replace("refs/tags/", "")
                tags.append(tag)
        return sorted(set(tags))
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="git ls-remote timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.get("/consume-file")
async def consume_file(token: str):
    """
    Consume a single-use file token and stream the file from the workspace.
    No authentication is required as it relies on the opaque, single-use token.
    """
    redis = await get_redis()
    metadata = await consume_file_token(redis, token)
    if not metadata:
        raise HTTPException(status_code=403, detail="Invalid or expired token")

    scope = metadata.get("scope", "agent")
    scope_id = metadata.get("scope_id")
    path = metadata.get("path")

    if not all([scope_id, path]):
        raise HTTPException(status_code=400, detail="Invalid token metadata")

    # Internal auth for workspace
    settings = get_settings()
    ws_token = create_internal_token("core-api", scopes=["workspace"], expires_minutes=1)
    
    # Forward the request to workspace
    url = f"{settings.workspace_url}/download"
    params = {
        "agent_id": scope_id,  # Workspace /download expects agent_id as effective_scope_id
        "path": path,
        "scope": scope,
        "scope_id": scope_id
    }
    
    async def _stream_file():
        async with httpx.AsyncClient(timeout=600.0) as client:
            async with client.stream("GET", url, params=params, headers={"X-Internal-Auth": ws_token}) as resp:
                if resp.status_code != 200:
                    logger.error("skills.consume_file_workspace_failed", status=resp.status_code, token=token, path=path)
                    return
                async for chunk in resp.aiter_bytes():
                    yield chunk

    return StreamingResponse(_stream_file(), media_type="application/octet-stream")


@router.patch("/{skill_id}")
async def patch_skill(
    skill_id: str,
    request: SkillPatchRequest,
    admin_key: str = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db),
):
    """Update mutable skill metadata (update_policy, source_ref, etc.)."""
    from isli_core.models import SkillRegistry as SkillRegistryModel
    result = await db.execute(
        select(SkillRegistryModel).where(SkillRegistryModel.id == skill_id)
    )
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found")

    if request.update_policy is not None:
        allowed = {"auto", "manual", "pinned"}
        if request.update_policy not in allowed:
            raise HTTPException(status_code=400, detail=f"update_policy must be one of {allowed}")
        skill.update_policy = request.update_policy
    if request.source_ref is not None:
        skill.source_ref = request.source_ref

    await db.commit()
    return {
        "status": "patched",
        "skill_id": skill_id,
        "update_policy": skill.update_policy,
        "source_ref": skill.source_ref,
    }


@router.post("/{skill_name}/{action}")
async def skill_proxy(
    skill_name: str,
    action: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    base_url = SKILL_REGISTRY.get(skill_name)
    is_dynamic = False
    is_db_external = False

    if not base_url:
        # Check DB-backed external skills first so container skills shadow stale filesystem copies
        db_registry = await skill_manager.get_registry()
        if skill_name in db_registry:
            base_url = db_registry[skill_name]
            is_db_external = True
        # Fallback to legacy dynamic skills
        elif skill_name in skill_manager.get_skill_metadata():
            is_dynamic = True
        else:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not registered")

    # Verify internal auth header from caller
    try:
        SkillProxyAuth.verify(request)
    except HTTPException:
        # In dev mode ONLY, allow unauthenticated if no header is present
        if get_settings().isli_env == "development" and request.headers.get("X-Internal-Auth") is None:
            logger.warning("skills.dev_mode_unauthenticated", skill=skill_name)
        else:
            raise

    body_bytes = await request.body()

    # Dynamic skill handler
    if is_dynamic:
        handler = skill_manager.get_handler(skill_name)
        if not handler:
            raise HTTPException(
                status_code=500,
                detail=f"Handler for dynamic skill '{skill_name}' could not be loaded",
            )

        try:
            body_json = (
                json.loads(body_bytes.decode("utf-8", errors="ignore"))
                if body_bytes
                else {}
            )
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail="Invalid JSON body") from e

        # Assume dynamic skills have a 'handle' function or similar
        if hasattr(handler, "handle"):
            try:
                # Dynamic skills can be async or sync
                if asyncio.iscoroutinefunction(handler.handle):
                    return await handler.handle(action, body_json, db)
                else:
                    return handler.handle(action, body_json, db)
            except Exception as e:
                logger.error(
                    "skills.dynamic_handler_failed",
                    skill=skill_name,
                    action=action,
                    error=str(e),
                )
                raise HTTPException(
                    status_code=500,
                    detail=f"Dynamic skill execution failed: {str(e)}",
                ) from e
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Dynamic skill '{skill_name}' missing 'handle' function",
            )

    # Inline handlers for memory skills (executed directly in Core, no external proxy)
    if base_url == "inline":
        try:
            body_json = json.loads(body_bytes.decode("utf-8", errors="ignore")) if body_bytes else {}
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON body")

        agent_id = body_json.get("agent_id")
        if not agent_id:
            raise HTTPException(status_code=400, detail="Missing agent_id in request body")
        collection_name = f"agent_{agent_id}"

        if skill_name == "memory-save" and action == "save":
            content = body_json.get("content")
            if not content:
                raise HTTPException(status_code=400, detail="Missing content in request body")
            fact_id = str(uuid4())
            try:
                await chroma.save_fact(
                    collection_name=collection_name,
                    fact_id=fact_id,
                    content=content,
                    metadata=body_json.get("metadata"),
                    embedding=body_json.get("embedding"),
                )
                return {"id": fact_id, "collection": collection_name, "status": "saved"}
            except Exception as exc:
                logger.error("skills.memory_save_failed", agent_id=agent_id, error=str(exc))
                raise HTTPException(status_code=500, detail=f"Failed to save memory: {exc}")

        if skill_name == "memory-delete" and action == "delete":
            fact_id = body_json.get("fact_id")
            if not fact_id:
                raise HTTPException(status_code=400, detail="Missing fact_id in request body")
            try:
                await chroma.delete_fact(collection_name=collection_name, fact_id=fact_id)
                return {"status": "deleted", "fact_id": fact_id}
            except Exception as exc:
                logger.error("skills.memory_delete_failed", agent_id=agent_id, fact_id=fact_id, error=str(exc))
                raise HTTPException(status_code=500, detail=f"Failed to delete memory: {exc}")

        if skill_name == "memory-search" and action == "search":
            query_text = body_json.get("query_text")
            if not query_text:
                raise HTTPException(status_code=400, detail="Missing query_text in request body")
            try:
                results = await chroma.search_facts(
                    collection_name=collection_name,
                    query_text=query_text,
                    query_embedding=body_json.get("query_embedding"),
                    limit=body_json.get("limit", 5),
                    metadata_filter=body_json.get("metadata_filter"),
                )
                return results
            except Exception as exc:
                logger.error("skills.memory_search_failed", agent_id=agent_id, query=query_text, error=str(exc))
                raise HTTPException(status_code=500, detail="Failed to search memory")

        if skill_name == "send-message" and action == "send":
            agent_id = body_json.get("agent_id")
            channel = body_json.get("channel")
            channel_user_id = body_json.get("channel_user_id")
            text = body_json.get("text")
            audio_b64 = body_json.get("audio_b64")
            if not all([agent_id, channel, channel_user_id, text]):
                raise HTTPException(status_code=400, detail="Missing required fields: agent_id, channel, channel_user_id, text")

            # Validate audio_b64 size at schema level (5 MB raw ~ 6.7 MB base64)
            if audio_b64 and len(audio_b64) > 6_700_000:
                raise HTTPException(status_code=413, detail="audio_b64 exceeds maximum size of 5 MB decoded")

            from sqlalchemy import select
            from isli_core.models import Agent, Session, ChannelMessage
            from isli_core.retry import exponential_backoff
            from datetime import datetime, timezone, timedelta

            # 1. Verify agent exists and channel is assigned
            result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None)))
            agent = result.scalar_one_or_none()
            if not agent:
                raise HTTPException(status_code=404, detail="Agent not found")
            if channel not in (agent.channels or []):
                raise HTTPException(status_code=403, detail="Channel not assigned to agent")

            # 2. Find or create canonical session (same convention as channels.py webhook)
            session_id = f"sess_{channel}_{agent_id}_{channel_user_id}"
            now = datetime.now(timezone.utc)
            result = await db.execute(select(Session).where(Session.id == session_id, Session.deleted_at.is_(None)))
            sess = result.scalar_one_or_none()

            if not sess:
                soft_deleted_result = await db.execute(select(Session).where(Session.id == session_id))
                soft_deleted = soft_deleted_result.scalar_one_or_none()
                if soft_deleted:
                    soft_deleted.deleted_at = None
                    soft_deleted.status = "ready"
                    soft_deleted.expires_at = now + timedelta(hours=24)
                    soft_deleted.last_activity_at = now
                    sess = soft_deleted
                else:
                    sess = Session(
                        id=session_id,
                        agent_id=agent_id,
                        user_id=channel_user_id,
                        channel=channel,
                        messages=[],
                        consent_given=True,
                        consent_at=now,
                        expires_at=now + timedelta(hours=24),
                        status="ready",
                    )
                    db.add(sess)
            else:
                sess.expires_at = now + timedelta(hours=24)
                sess.last_activity_at = now

            # --- Audio handling for send-message skill ---
            audio_url: str | None = None
            audio_b64_for_channels = audio_b64
            if audio_b64_for_channels:
                try:
                    MAX_AUDIO_BYTES = 5 * 1024 * 1024
                    audio_bytes = base64.b64decode(audio_b64_for_channels)
                    if len(audio_bytes) > MAX_AUDIO_BYTES:
                        logger.warning(
                            "skills.send_message_audio_too_large",
                            agent_id=agent_id,
                            size=len(audio_bytes),
                        )
                        audio_b64_for_channels = None
                    else:
                        from isli_core.routers.workspaces import upload_bytes_to_workspace
                        audio_filename = f"{uuid4()}.wav"
                        workspace_path = f"_attachments/audio/{session_id}/{audio_filename}"
                        await upload_bytes_to_workspace(
                            agent_id=agent_id,
                            path=workspace_path,
                            data=audio_bytes,
                            scope="attachment",
                            scope_id=session_id,
                        )
                        audio_url = f"/v1/sessions/{session_id}/audio/{audio_filename}"
                        logger.info(
                            "skills.send_message_audio_uploaded",
                            agent_id=agent_id,
                            filename=audio_filename,
                            size=len(audio_bytes),
                        )
                except Exception as exc:
                    logger.warning("skills.send_message_audio_upload_failed", agent_id=agent_id, error=str(exc))
                    audio_b64_for_channels = None

            msg = {"role": "assistant", "content": text, "timestamp": now.isoformat()}
            if audio_url:
                msg["audio_url"] = audio_url
            sess.messages = (sess.messages or []) + [msg]
            sess.last_message_at = now
            await db.commit()
            await db.refresh(sess)

            # 3. Audit outbound message
            channel_msg = ChannelMessage(
                session_id=session_id,
                sequence_number=len(sess.messages),
                channel=channel,
                direction="outbound",
                content=text,
                raw_payload={
                    "source": "send_message_skill",
                    "agent_id": agent_id,
                    "audio_url": audio_url,
                },
            )
            db.add(channel_msg)
            await db.commit()

            # 4. Forward to channels service (only for external channels)
            if channel != "web":
                settings = get_settings()

                async def _send_to_channels():
                    payload_channels = {
                        "channel": channel,
                        "channel_user_id": channel_user_id,
                        "text": text,
                        "agent_id": agent_id,
                    }
                    if audio_b64_for_channels:
                        payload_channels["audio_b64"] = audio_b64_for_channels
                    async with httpx.AsyncClient() as client:
                        resp = await client.post(
                            f"{settings.channels_url}/send",
                            json=payload_channels,
                            headers={"X-Internal-Auth": create_internal_token("core", scopes=["channels:send"], expires_minutes=5)},
                            timeout=10.0,
                        )
                        resp.raise_for_status()

                try:
                    from isli_core.dynamic_config import get_setting
                    max_retries = await get_setting(db, "default_max_retries", scope="general", default=3)
                    base_delay = await get_setting(db, "default_base_delay_seconds", scope="general", default=1.0)
                    max_delay = await get_setting(db, "default_max_delay_seconds", scope="general", default=10.0)
                    await exponential_backoff(
                        _send_to_channels,
                        max_retries=max_retries,
                        base_delay=base_delay,
                        max_delay=max_delay,
                    )
                except Exception as exc:
                    logger.error("skills.send_message_failed", agent_id=agent_id, channel=channel, error=str(exc))
            else:
                logger.debug(
                    "skills.send_message.skip_external_forward",
                    agent_id=agent_id,
                    channel=channel
                )

            return {"status": "sent", "session_id": session_id}

        if skill_name == "notify-user" and action == "send":
            agent_id = body_json.get("agent_id")
            user_id = body_json.get("user_id")
            title = body_json.get("title")
            message = body_json.get("message", "")
            priority = body_json.get("priority", "normal")

            if not all([agent_id, user_id, title]):
                raise HTTPException(status_code=400, detail="Missing required fields: agent_id, user_id, title")

            # Rate limit check (same logic as notifications router)
            AGENT_NOTIFY_RATE_LIMIT = 20
            try:
                redis = await get_redis()
                rate_key = f"notif:agent_rate:{agent_id}:{user_id}"
                count = await redis.incr(rate_key)
                if count == 1:
                    await redis.expire(rate_key, 3600)
                if count > AGENT_NOTIFY_RATE_LIMIT:
                    raise HTTPException(status_code=429, detail="Notification rate limit exceeded for this agent (max 20/hour per user)")
            except HTTPException:
                raise
            except Exception as exc:
                logger.warning("skills.notify_user_rate_limit_redis_failed", error=str(exc))

            from isli_core.models import Notification
            from datetime import datetime, timezone

            notif = Notification(
                user_id=user_id,
                event_type="agent:proactive",
                category=priority,
                title=title,
                body=message or None,
                agent_id=agent_id,
            )
            db.add(notif)
            await db.commit()
            await db.refresh(notif)

            # Emit WS event
            from isli_core.event_manager import EventManager
            await EventManager.emit(
                "notification:new",
                {
                    "notification_id": notif.id,
                    "user_id": user_id,
                    "event_type": "agent:proactive",
                    "category": priority,
                    "title": title,
                    "body": message,
                    "created_at": notif.created_at.isoformat() if notif.created_at else None,
                    "agent_id": agent_id,
                },
            )

            return {"ok": True, "notification_id": notif.id}

        if skill_name == "shared-promote-file-workspace" and action == "promote":
            agent_id = body_json.get("agent_id")
            workspace_id = body_json.get("workspace_id")
            source_path = body_json.get("source_path")
            target_path = body_json.get("target_path")
            delete_source = body_json.get("delete_source", False)
            if not all([agent_id, workspace_id, source_path, target_path]):
                raise HTTPException(status_code=400, detail="Missing required fields: agent_id, workspace_id, source_path, target_path")

            from sqlalchemy import select
            from isli_core.models import SharedWorkspace
            result = await db.execute(
                select(SharedWorkspace).where(
                    SharedWorkspace.id == workspace_id,
                    SharedWorkspace.deleted_at.is_(None),
                )
            )
            workspace = result.scalar_one_or_none()
            if not workspace:
                raise HTTPException(status_code=404, detail="Shared workspace not found")
            if agent_id != workspace.owner_id and agent_id not in (workspace.members or []):
                raise HTTPException(status_code=403, detail="Access denied to this shared workspace")

            settings = get_settings()
            url = f"{settings.workspace_url}/shared/promote"
            token = create_internal_token("core-api", scopes=["workspace"], expires_minutes=1)
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    json={
                        "agent_id": agent_id,
                        "source_scope": "agent",
                        "source_scope_id": agent_id,
                        "source_path": source_path,
                        "target_workspace_id": workspace_id,
                        "target_path": target_path,
                        "delete_source": bool(delete_source),
                        "quota_bytes": workspace.quota_bytes,
                    },
                    headers={"X-Internal-Auth": token},
                )
                if resp.status_code != 200:
                    raise HTTPException(status_code=resp.status_code, detail=resp.text)

            from isli_core.audit_writer import AuditWriter
            await AuditWriter.write(
                db,
                actor_type="agent",
                actor_id=agent_id,
                action="shared_promote_file_workspace",
                target_type="shared_workspace",
                target_id=workspace_id,
                payload={"source_path": source_path, "target_path": target_path},
            )
            await db.commit()
            return {"status": "ok", "workspace_id": workspace_id, "target_path": target_path}

        if skill_name == "shared-workspace-info" and action == "info":
            agent_id = body_json.get("agent_id")
            workspace_id = body_json.get("workspace_id")
            if not all([agent_id, workspace_id]):
                raise HTTPException(status_code=400, detail="Missing required fields: agent_id, workspace_id")

            from sqlalchemy import select
            from isli_core.models import SharedWorkspace
            result = await db.execute(
                select(SharedWorkspace).where(
                    SharedWorkspace.id == workspace_id,
                    SharedWorkspace.deleted_at.is_(None),
                )
            )
            workspace = result.scalar_one_or_none()
            if not workspace:
                raise HTTPException(status_code=404, detail="Shared workspace not found")
            if agent_id != workspace.owner_id and agent_id not in (workspace.members or []):
                raise HTTPException(status_code=403, detail="Access denied to this shared workspace")

            return {
                "workspace_id": workspace.id,
                "name": workspace.name,
                "description": workspace.description,
                "owner_id": workspace.owner_id,
                "members": workspace.members or [],
                "quota_bytes": workspace.quota_bytes,
                "root_path": f"_shared/{workspace.id}",
                "created_at": workspace.created_at.isoformat() if workspace.created_at else None,
                "updated_at": workspace.updated_at.isoformat() if workspace.updated_at else None,
            }

        if skill_name == "get-secret" and action == "get":
            secret_name = body_json.get("name")
            if not secret_name:
                raise HTTPException(status_code=400, detail="Missing name in request body")

            from isli_core.secrets_service import get_secret_value
            from isli_core.audit_writer import AuditWriter

            # Verify secret exists for this agent
            exists = await get_secret_value(db, agent_id, secret_name)
            if exists is None:
                raise HTTPException(status_code=404, detail=f"Secret '{secret_name}' not found")

            # Audit every secret reference read (value never logged)
            await AuditWriter.write(
                session=db,
                actor_type="agent",
                actor_id=agent_id,
                action="secret.reference_read",
                target_type="secret",
                target_id=secret_name,
                payload={"agent_id": agent_id, "secret_name": secret_name},
            )
            await db.commit()
            # Return placeholder for server-side injection
            return {"status": "ok", "name": secret_name, "value": f"[[secret:{secret_name}]]"}

        if skill_name == "create-kanban-task" and action == "create":
            title = body_json.get("title")
            if not title:
                raise HTTPException(status_code=400, detail="Missing title in request body")

            from isli_core.routers.tasks import _create_task_core, TaskCreate, TaskOut
            from datetime import datetime

            scheduled_at_raw = body_json.get("scheduled_at")
            scheduled_at: datetime | None = None
            if scheduled_at_raw:
                try:
                    scheduled_at = datetime.fromisoformat(scheduled_at_raw.replace("Z", "+00:00"))
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=f"Invalid scheduled_at format: {exc}")

            payload = TaskCreate(
                title=title,
                description=body_json.get("description"),
                type=body_json.get("task_type", "task"),
                priority=body_json.get("priority", 3),
                agent_id=body_json.get("target_agent_id"),
                created_by=agent_id,
                input=body_json.get("input_data", ""),
                parent_task_id=body_json.get("parent_task_id"),
                scheduled_at=scheduled_at,
                cron_expression=body_json.get("cron_expression"),
            )

            estop = getattr(request.app.state, "estop", None)
            estop_active = estop.active if estop else False
            task = await _create_task_core(db, payload, estop_active=estop_active)
            return {
                "status": "created",
                "task": TaskOut.model_validate(task).model_dump(mode="json"),
            }

        if skill_name == "list-kanban-tasks" and action == "list":
            from isli_core.models import Task
            from isli_core.routers.tasks import TaskOut
            from sqlalchemy import select

            stmt = select(Task).where(Task.deleted_at.is_(None))
            if body_json.get("status"):
                stmt = stmt.where(Task.status == body_json.get("status"))
            if body_json.get("assignee_id"):
                stmt = stmt.where(Task.agent_id == body_json.get("assignee_id"))
            
            # Use tags if provided in body
            tags = body_json.get("tags")
            if tags:
                if isinstance(tags, str):
                    tags = [tags]
                for tag in tags:
                    stmt = stmt.where(Task.tags.contains([tag]))

            stmt = stmt.order_by(Task.created_at.desc())
            result = await db.execute(stmt)
            tasks = result.scalars().all()
            return [TaskOut.model_validate(t).model_dump(mode="json") for t in tasks]

        if skill_name == "update-kanban-task" and action == "update":
            task_id = body_json.get("task_id")
            if not task_id:
                raise HTTPException(status_code=400, detail="Missing task_id in request body")
            
            from isli_core.models import Task
            from isli_core.routers.tasks import TaskOut, VALID_STATUSES
            from isli_core.event_manager import EventManager
            from isli_core.audit_writer import AuditWriter
            from datetime import datetime, timezone

            result = await db.execute(select(Task).where(Task.id == task_id, Task.deleted_at.is_(None)))
            task = result.scalar_one_or_none()
            if not task:
                raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

            changes = {}
            new_status = body_json.get("new_status")
            if new_status:
                if new_status not in VALID_STATUSES:
                    raise HTTPException(status_code=400, detail=f"Invalid status: {new_status}")
                if task.status != new_status:
                    old_status = task.status
                    task.status = new_status
                    changes["status"] = new_status
                    if new_status == "doing":
                        task.started_at = datetime.now(timezone.utc)
                    if new_status in ("done", "failed"):
                        task.completed_at = datetime.now(timezone.utc)
                    
                    await EventManager.emit("task:moved", {
                        "task_id": task_id,
                        "from": old_status,
                        "to": new_status,
                        "task": TaskOut.model_validate(task).model_dump(mode="json")
                    })

            new_priority = body_json.get("new_priority")
            if new_priority is not None:
                task.priority = new_priority
                changes["priority"] = new_priority

            comment = body_json.get("comment")
            if comment:
                timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                addition = f"\n\n--- Handoff/Comment ({timestamp}) ---\n{comment}"
                task.description = (task.description or "") + addition
                changes["description_updated"] = True

            if changes:
                task.updated_at = datetime.now(timezone.utc)
                task.version += 1
                await db.commit()
                await db.refresh(task)
                
                await AuditWriter.write(
                    db, actor_type="agent", actor_id=agent_id, action="update_task_skill",
                    target_type="task", target_id=task.id,
                    payload={"changes": changes, "comment": comment},
                )
                await db.commit()
                
                await EventManager.emit("task:updated", {
                    "task_id": task_id,
                    "changes": changes,
                    "task": TaskOut.model_validate(task).model_dump(mode="json")
                })

            return {"status": "success", "task_id": task_id, "updated": bool(changes)}

        raise HTTPException(status_code=404, detail=f"Action '{action}' not found for skill '{skill_name}'")

    body = body_bytes
    body_text = body.decode("utf-8", errors="ignore") if body else ""

    # --- Server-Side Secret Injection ---
    try:
        body_json = json.loads(body_text) if body_text else {}
    except json.JSONDecodeError:
        body_json = {}

    agent_id = body_json.get("agent_id")
    if agent_id:
        # Determine authorized secret fields for this skill/action
        secret_fields = []
        file_fields = []
        meta = SKILL_METADATA.get(skill_name, {})
        if meta:
            secret_fields = meta.get("secret_fields", [])
            file_fields = meta.get("file_fields", [])
        elif is_db_external:
            manifest = await skill_manager.get_skill_manifest(skill_name)
            if manifest:
                for tool in manifest.get("tools", []):
                    if tool.get("name") == action:
                        secret_fields = tool.get("secret_fields", [])
                        file_fields = tool.get("file_fields", [])
                        break

        if secret_fields:
            from isli_core.secrets_service import get_secret_value
            from isli_core.audit_writer import AuditWriter
            
            modified = False
            for field in secret_fields:
                val = body_json.get(field)
                if isinstance(val, str) and val.startswith("[[secret:") and val.endswith("]]"):
                    secret_name = val[9:-2]
                    secret_val = await get_secret_value(db, agent_id, secret_name)
                    if secret_val:
                        body_json[field] = secret_val
                        modified = True
                        
                        # Audit the injection
                        await AuditWriter.write(
                            session=db,
                            actor_type="agent",
                            actor_id=agent_id,
                            action="secret.inject",
                            target_type="skill",
                            target_id=f"{skill_name}:{action}",
                            payload={"field": field, "secret_name": secret_name},
                        )

            if modified:
                await db.commit()
                body = json.dumps(body_json).encode("utf-8")
                # Update body_text for policy engine which uses it for scanning
                body_text = body.decode("utf-8", errors="ignore")

        if file_fields:
            from isli_core.audit_writer import AuditWriter
            redis = await get_redis()
            
            modified_files = False
            for field in file_fields:
                val = body_json.get(field)
                if isinstance(val, str) and val.startswith("[[file:") and val.endswith("]]"):
                    # Format: [[file:scope:scope_id:path]]
                    parts = val[7:-2].split(":", 2)
                    if len(parts) == 3:
                        f_scope, f_scope_id, f_path = parts
                        token = await create_file_token(redis, f_scope, f_scope_id, f_path)
                        
                        # Construct proxy URL
                        # Note: We use the request's base URL so the skill can reach core back
                        proxy_url = f"{str(request.base_url).rstrip('/')}/v1/skills/consume-file?token={token}"
                        body_json[field] = proxy_url
                        modified_files = True
                        
                        # Audit the injection
                        await AuditWriter.write(
                            session=db,
                            actor_type="agent",
                            actor_id=agent_id,
                            action="file.inject",
                            target_type="skill",
                            target_id=f"{skill_name}:{action}",
                            payload={"field": field, "scope": f_scope, "scope_id": f_scope_id, "path": f_path},
                        )

            if modified_files:
                body = json.dumps(body_json).encode("utf-8")
                body_text = body.decode("utf-8", errors="ignore")

    # Content scan on the raw (possibly injected) body text
    scan = ContentScanner.scan(body_text)
    if scan.blocked:
        raise HTTPException(status_code=403, detail=f"Content safety block: {scan.reason}")

    # Policy evaluation for skill invocation
    estop = getattr(request.app.state, "estop", None)
    estop_active = estop.active if estop else False

    decision = await PolicyEngine.evaluate(
        db,
        user_id="anonymous",
        input_text=body_text,
        agent_id=None,
        skill_name=skill_name,
        model_id=None,
        budget_exceeded=False,
        estop_active=estop_active,
    )
    if not decision.allow:
        detail: dict[str, Any] = {
            "detail": f"Policy block: {decision.reason}",
            "policy_decision": {
                "allow": decision.allow,
                "reason": decision.reason,
                "risk_score": decision.risk_score,
                "overrideable": decision.overrideable,
                "rule": decision.rule,
                "context_hash": decision.context_hash,
            },
        }
        if decision.overrideable:
            detail["override_request_url"] = "/v1/security/override-request"
        raise HTTPException(status_code=403, detail=detail)
    token = create_internal_token("core-api", scopes=["skill:proxy"], expires_minutes=5)
    headers = {
        "X-Internal-Auth": token,
        "Content-Type": request.headers.get("Content-Type", "application/json"),
    }

    from isli_core.verification.grounding import GroundingVerifier
    from isli_core.telemetry import get_verification_failure_counter

    url = f"{base_url}/{action}"

    async def _call_skill() -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, headers=headers, content=body)
            resp.raise_for_status()
            return resp.json()

    try:
        raw, result = await GroundingVerifier.verify_with_retry(
            skill_name, _call_skill, max_retries=3
        )

        # Notify isli-skills about usage for telemetry (Hygiene)
        # Avoid double-counting if the skill is already hosted by isli-skills (8100)
        SKILLS_SERVICE_URL = os.getenv("SKILL_WEB_FETCH_URL", "http://localhost:8100").rstrip("/")
        if result.is_valid and ":8100" not in base_url:
            async def _notify_usage():
                async with httpx.AsyncClient() as client:
                    token = create_internal_token("core-api", scopes=["skill:telemetry"], expires_minutes=1)
                    await client.post(
                        f"{SKILLS_SERVICE_URL}/skills/{skill_name}/usage",
                        headers={"X-Internal-Auth": token}
                    )
            asyncio.create_task(_notify_usage())

        # Phase 2: Local Skill Cleaning (Signal Harvesting)
        HEAVY_SKILLS = {"web-fetch", "shell-exec", "web-browse-snapshot", "web-browse-vision"}
        if result.is_valid and skill_name in HEAVY_SKILLS:
            logger.info("skills.harvesting.cleaning", skill=skill_name)
            # Use the action or a generic goal for cleaning
            cleaned = await KeeperClient.clean_skill_output(
                str(raw),
                goal=f"Extract relevant data for action '{action}'"
            )
            return {"status": "ok", "skill": skill_name, "action": action, "result": cleaned}

    except Exception as exc:
        logger.error("skills.proxy_unexpected_error", skill=skill_name, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Unexpected skill proxy error: {exc}") from exc

    if not result.is_valid:
        from isli_core.telemetry import get_skill_invocation_error_counter
        reason_lower = result.reason.lower() if result.reason else ""

        # Preserve 4xx client errors so the agent knows it sent bad arguments
        status_code = 502
        if "422" in reason_lower or "unprocessable entity" in reason_lower:
            status_code = 422
        elif "400" in reason_lower or "bad request" in reason_lower:
            status_code = 400
        elif "403" in reason_lower or "forbidden" in reason_lower:
            status_code = 403
        elif "404" in reason_lower or "not found" in reason_lower:
            status_code = 404

        if "httpx" in reason_lower and "status" in reason_lower:
            get_skill_invocation_error_counter().add(
                1, {"skill": skill_name, "reason": "http_error"}
            )
        elif "unreachable" in reason_lower or "connect" in reason_lower or "timeout" in reason_lower:
            get_skill_invocation_error_counter().add(
                1, {"skill": skill_name, "reason": "unreachable"}
            )
        get_verification_failure_counter().add(
            1, {"skill": skill_name, "reason": result.reason}
        )
        logger.error("skills.verification_failed", skill=skill_name, reason=result.reason)
        raise HTTPException(
            status_code=status_code,
            detail={"success": False, "error": result.reason, "skill": skill_name},
        )

    return raw
