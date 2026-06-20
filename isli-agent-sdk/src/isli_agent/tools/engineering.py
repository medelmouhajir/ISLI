from typing import Any

from isli_agent.client import CoreClient


def _get_tool_desc(name: str, default: str) -> str:
    """Load a tool description from prompts.yaml if available."""
    try:
        from isli_agent.prompts_loader import get_prompts
        return get_prompts()["agent"]["tool_descriptions"].get(name, default)
    except Exception:
        return default


async def create_engineering_plan(
    agent_id: str,
    objective: str,
    steps: list[str],
    context: str | None = None,
    filename: str = "PLAN.md",
    core_client: CoreClient | None = None
) -> dict[str, Any]:
    """Generate a structured Markdown implementation plan and save it to the workspace."""
    if core_client is None:
        raise ValueError("core_client is required")

    markdown_plan = f"# Implementation Plan: {objective}\n\n"
    if context:
        markdown_plan += f"## Context\n{context}\n\n"

    markdown_plan += "## Steps\n"
    for i, step in enumerate(steps, 1):
        markdown_plan += f"{i}. {step}\n"

    from isli_agent.tools.workspace import file_write
    await file_write(
        agent_id=agent_id,
        path=filename,
        content=markdown_plan,
        core_client=core_client
    )

    return {
        "status": "plan_created",
        "filename": filename,
        "step_count": len(steps),
        "preview": markdown_plan[:200] + "..." if len(markdown_plan) > 200 else markdown_plan
    }


async def test_skill(
    workspace_path: str,
    agent_id: str,
    core_client: CoreClient | None = None
) -> dict[str, Any]:
    """Dry-run build a USR skill from the agent workspace before registration.

    The skill directory must contain a valid `isli-skill.yaml` manifest and a
    `Dockerfile`. Core validates the manifest and performs a dry-run Docker build
    (no container is started).
    """
    if core_client is None:
        raise ValueError("core_client is required")

    try:
        result = await core_client.invoke_skill(
            skill_name="test-skill",
            action="test",
            payload={"workspace_path": workspace_path, "agent_id": agent_id},
        )
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


async def register_skill(
    workspace_path: str,
    agent_id: str,
    task_id: str | None = None,
    core_client: CoreClient | None = None
) -> dict[str, Any]:
    """Register a workspace skill into the USR lifecycle.

    Core reads the `skill_id` from the `isli-skill.yaml` manifest in the given
    workspace directory, copies the files into the USR installed-skills store,
    builds and starts the container, and probes the `/health` endpoint.
    """
    if core_client is None:
        raise ValueError("core_client is required")

    try:
        reg_result = await core_client.invoke_skill(
            skill_name="register-skill",
            action="register",
            payload={"workspace_path": workspace_path, "agent_id": agent_id},
        )

        if task_id:
            await core_client.move_task(task_id, "review")

        return {
            "status": reg_result.get("status", "registered"),
            "skill_id": reg_result.get("skill_id"),
            "details": reg_result,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def update_skill(
    workspace_path: str,
    agent_id: str,
    core_client: CoreClient | None = None
) -> dict[str, Any]:
    """Update an existing USR skill from the agent workspace.

    Core performs a clean sync from the workspace directory, rebuilds the skill
    container, and executes a blue/green swap. On probe failure the previous
    container remains active and the source is rolled back.
    """
    if core_client is None:
        raise ValueError("core_client is required")

    try:
        result = await core_client.invoke_skill(
            skill_name="update-skill",
            action="update",
            payload={"workspace_path": workspace_path, "agent_id": agent_id},
        )
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


PLAN_DEF = {
    "type": "function",
    "function": {
        "name": "create_engineering_plan",
        "description": "Generate a structured implementation plan (PLAN.md) "
                     "before starting complex tasks.",
        "parameters": {
            "type": "object",
            "properties": {
                "objective": {
                    "type": "string",
                    "description": "The main goal or feature to be implemented",
                },
                "steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of logical steps to achieve the objective",
                },
                "context": {
                    "type": "string",
                    "description": "Additional technical context or architectural notes",
                },
                "filename": {
                    "type": "string",
                    "description": "Name of the plan file (defaults to PLAN.md)",
                    "default": "PLAN.md"
                }
            },
            "required": ["objective", "steps"],
        },
    },
}

TEST_SKILL_DEF = {
    "type": "function",
    "function": {
        "name": "test_skill",
        "description": _get_tool_desc(
            "test_skill",
            "Dry-run build a USR skill from a workspace directory. "
            "The directory must contain isli-skill.yaml and a Dockerfile. "
            "No container is started.",
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "workspace_path": {
                    "type": "string",
                    "description": "Relative path to the USR skill directory "
                                 "in the agent workspace (e.g., 'skills/my-skill')",
                },
            },
            "required": ["workspace_path"],
        },
    },
}

REGISTER_SKILL_DEF = {
    "type": "function",
    "function": {
        "name": "register_skill",
        "description": _get_tool_desc(
            "register_skill",
            "Install a USR skill from a workspace directory into the runtime. "
            "The skill_id is read from isli-skill.yaml. "
            "Call this ONLY after a successful test_skill.",
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "workspace_path": {
                    "type": "string",
                    "description": "Relative path to the USR skill directory "
                                 "in the agent workspace (e.g., 'skills/my-skill')",
                },
                "task_id": {
                    "type": "string",
                    "description": "The current task ID "
                                 "(to automatically move it to 'review' status)",
                }
            },
            "required": ["workspace_path"],
        },
    },
}

UPDATE_SKILL_DEF = {
    "type": "function",
    "function": {
        "name": "update_skill",
        "description": _get_tool_desc(
            "update_skill",
            "Update an installed USR skill from a workspace directory. "
            "Core performs a clean sync, builds a new image, runs a blue/green "
            "container swap, and rolls back automatically if the new container "
            "fails its health probe.",
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "workspace_path": {
                    "type": "string",
                    "description": "Relative path to the USR skill directory "
                                 "in the agent workspace (e.g., 'skills/my-skill')",
                },
            },
            "required": ["workspace_path"],
        },
    },
}
