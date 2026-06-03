from typing import Any, Optional, List
from isli_agent.client import CoreClient
from .workspace import file_write


def _get_tool_desc(name: str, default: str) -> str:
    try:
        from isli_agent.prompts_loader import get_prompts
        return get_prompts()["agent"]["tool_descriptions"].get(name, default)
    except Exception:
        return default


async def create_engineering_plan(
    agent_id: str,
    objective: str,
    steps: List[str],
    context: Optional[str] = None,
    filename: str = "PLAN.md",
    core_client: CoreClient = None
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
    
    # Write to workspace
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


async def test_skill_code(
    code: str,
    test_payload: dict[str, Any],
    core_client: CoreClient = None
) -> dict[str, Any]:
    """Dry-run test dynamic skill code in a sandbox before registration."""
    if core_client is None:
        raise ValueError("core_client is required")

    try:
        # Call test-skill through Core proxy
        result = await core_client.invoke_skill(
            skill_name="test-skill",
            action="test",
            payload={"code": code, "payload": test_payload}
        )
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


async def register_skill(
    name: str,
    workspace_path: str,
    description: str,
    task_id: Optional[str] = None,
    agent_id: str = None,
    core_client: CoreClient = None
) -> dict[str, Any]:
    """Register a new dynamic skill and move the current task to 'review' status."""
    if core_client is None:
        raise ValueError("core_client is required")

    payload = {
        "name": name,
        "workspace_path": workspace_path,
        "agent_id": agent_id,
        "description": description
    }

    try:
        # 1. Register with Skills service via Core proxy
        reg_result = await core_client.invoke_skill(
            skill_name="register-skill",
            action="register",
            payload=payload
        )

        # 2. Move task to review column if task_id is provided
        if task_id:
            await core_client.move_task(task_id, "review")

        return {
            "status": "registered_pending_review",
            "skill_name": name,
            "details": reg_result
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def update_skill(
    name: str,
    description: Optional[str] = None,
    workspace_path: Optional[str] = None,
    category: Optional[str] = None,
    endpoint: Optional[str] = None,
    health_endpoint: Optional[str] = None,
    agent_id: Optional[str] = None,
    core_client: CoreClient = None
) -> dict[str, Any]:
    """Update metadata of an existing dynamic skill."""
    if core_client is None:
        raise ValueError("core_client is required")

    payload: dict[str, Any] = {"name": name}
    if description is not None:
        payload["description"] = description
    if workspace_path is not None:
        payload["workspace_path"] = workspace_path
    if category is not None:
        payload["category"] = category
    if endpoint is not None:
        payload["endpoint"] = endpoint
    if health_endpoint is not None:
        payload["health_endpoint"] = health_endpoint
    if agent_id is not None:
        payload["agent_id"] = agent_id

    try:
        result = await core_client.invoke_skill(
            skill_name="update-skill",
            action="update",
            payload=payload
        )
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


PLAN_DEF = {
    "type": "function",
    "function": {
        "name": "create_engineering_plan",
        "description": _get_tool_desc(
            "create_engineering_plan",
            "Generate a structured implementation plan (PLAN.md) before starting complex tasks."
        ),
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
        "description": "Dry-run test dynamic skill code in a sandbox with a test payload.",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "The Python code for the dynamic skill (must define 'async def run(payload: dict)')",
                },
                "test_payload": {
                    "type": "object",
                    "description": "JSON payload to pass to the skill's 'run' function",
                }
            },
            "required": ["code", "test_payload"],
        },
    },
}

REGISTER_SKILL_DEF = {
    "type": "function",
    "function": {
        "name": "register_skill",
        "description": "Register a new dynamic skill and submit it for human review. Call this ONLY after successful testing.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Unique name for the skill (e.g., 'csv-parser')",
                },
                "workspace_path": {
                    "type": "string",
                    "description": "Relative path to the skill's .py file in the agent workspace",
                },
                "description": {
                    "type": "string",
                    "description": "Clear explanation of what the skill does and its schema",
                },
                "task_id": {
                    "type": "string",
                    "description": "The current task ID (to automatically move it to 'review' status)",
                }
            },
            "required": ["name", "workspace_path", "description"],
        },
    },
}

UPDATE_SKILL_DEF = {
    "type": "function",
    "function": {
        "name": "update_skill",
        "description": "Update metadata of an existing dynamic skill. Only provided fields are changed; usage stats and creation time are preserved.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Unique name of the skill to update",
                },
                "description": {
                    "type": "string",
                    "description": "New description for the skill",
                },
                "workspace_path": {
                    "type": "string",
                    "description": "New relative path to the skill's .py file in the agent workspace",
                },
                "category": {
                    "type": "string",
                    "description": "New category for the skill (e.g., 'web', 'content', 'engineering')",
                },
                "endpoint": {
                    "type": "string",
                    "description": "New HTTP endpoint URL for the skill",
                },
                "health_endpoint": {
                    "type": "string",
                    "description": "New health check endpoint URL",
                },
                "agent_id": {
                    "type": "string",
                    "description": "New owning agent ID",
                }
            },
            "required": ["name"],
        },
    },
}
