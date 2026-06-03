from typing import Any, Optional
from isli_agent.client import CoreClient


def _get_tool_desc(name: str, default: str) -> str:
    try:
        from isli_agent.prompts_loader import get_prompts
        return get_prompts()["agent"]["tool_descriptions"].get(name, default)
    except Exception:
        return default


async def create_kanban_task(
    agent_id: str,
    title: str,
    description: Optional[str] = None,
    task_type: str = "task",
    priority: int = 3,
    target_agent_id: Optional[str] = None,
    parent_task_id: Optional[str] = None,
    input_data: str = "",
    core_client: CoreClient = None
) -> dict[str, Any]:
    """Create a new task in the Kanban board for self-delegation or delegating to others."""
    if core_client is None:
        raise ValueError("core_client is required")

    payload = {
        "title": title,
        "description": description,
        "type": task_type,
        "priority": priority,
        "agent_id": target_agent_id,
        "created_by": agent_id,
        "parent_task_id": parent_task_id,
        "input": input_data,
    }

    task = await core_client.create_task(payload)
    return {
        "status": "created",
        "task_id": task.id,
        "title": task.title,
        "status": task.status,
        "assigned_to": task.agent_id
    }


CREATE_KANBAN_TASK_DEF = {
    "type": "function",
    "function": {
        "name": "create_kanban_task",
        "description": _get_tool_desc(
            "create_kanban_task",
            "Create a new task in the Kanban board. Use this to delegate work to yourself or another agent."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short, descriptive title of the task",
                },
                "description": {
                    "type": "string",
                    "description": "Detailed explanation of what needs to be done",
                },
                "task_type": {
                    "type": "string",
                    "description": "Category of the task (e.g., 'research', 'code', 'review')",
                    "default": "task"
                },
                "priority": {
                    "type": "integer",
                    "description": "Priority level (1=highest, 5=lowest)",
                    "default": 3
                },
                "target_agent_id": {
                    "type": "string",
                    "description": "ID of the agent to assign this task to. Omit for unassigned 'inbox' tasks.",
                },
                "parent_task_id": {
                    "type": "string",
                    "description": "ID of the current task if this is a sub-task",
                },
                "input_data": {
                    "type": "string",
                    "description": "Specific input or context required to start the task",
                }
            },
            "required": ["title"],
        },
    },
}
