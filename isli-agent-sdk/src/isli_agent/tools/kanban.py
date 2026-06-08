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
    scheduled_at: Optional[str] = None,
    cron_expression: Optional[str] = None,
    core_client: CoreClient = None
) -> dict[str, Any]:
    """Create a new task in the Kanban board for self-delegation or delegating to others.

    Optional scheduling:
    - scheduled_at: ISO 8601 datetime (e.g., "2026-06-07T14:00:00Z") for a one-time delayed task.
    - cron_expression: Standard cron string (e.g., "0 */6 * * *") for recurring tasks.
      Minimum interval enforced by Core is 5 minutes.
    """
    if core_client is None:
        raise ValueError("core_client is required")

    payload: dict[str, Any] = {
        "title": title,
        "description": description,
        "type": task_type,
        "priority": priority,
        "agent_id": target_agent_id,
        "created_by": agent_id,
        "parent_task_id": parent_task_id,
        "input": input_data,
    }
    if scheduled_at is not None:
        payload["scheduled_at"] = scheduled_at
    if cron_expression is not None:
        payload["cron_expression"] = cron_expression

    task = await core_client.create_task(payload)
    return {
        "status": "created",
        "task_id": task.id,
        "title": task.title,
        "status": task.status,
        "assigned_to": task.agent_id,
        "scheduled_at": task.scheduled_at.isoformat() if task.scheduled_at else None,
        "cron_expression": task.cron_expression,
    }


async def list_kanban_tasks(
    status: Optional[str] = None,
    assignee_id: Optional[str] = None,
    core_client: CoreClient = None
) -> list[dict[str, Any]]:
    """Query the Kanban board for tasks based on status or assignee."""
    if core_client is None:
        raise ValueError("core_client is required")

    tasks = await core_client.list_tasks(status=status, agent_id=assignee_id)
    return [
        {
            "id": t.id,
            "title": t.title,
            "status": t.status,
            "priority": t.priority,
            "agent_id": t.agent_id,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "tags": t.tags,
        }
        for t in tasks
    ]


async def update_kanban_task(
    task_id: str,
    new_status: Optional[str] = None,
    new_priority: Optional[int] = None,
    comment: Optional[str] = None,
    core_client: CoreClient = None
) -> dict[str, Any]:
    """Update an existing Kanban task's status, priority, or append a comment/handoff note."""
    if core_client is None:
        raise ValueError("core_client is required")

    payload: dict[str, Any] = {}
    if new_priority is not None:
        payload["priority"] = new_priority
    
    # Handle status change
    if new_status:
        # Move task is a separate call in CoreClient to handle state transitions correctly
        await core_client.move_task(task_id, new_status)
    
    # Handle comment (append to description)
    if comment:
        task = await core_client.get_task(task_id)
        from datetime import datetime, timezone
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        addition = f"\n\n--- Handoff/Comment ({timestamp}) ---\n{comment}"
        payload["description"] = (task.description or "") + addition

    if payload:
        updated_task = await core_client.update_task(task_id, payload)
        return {
            "status": "updated",
            "task_id": updated_task.id,
            "new_status": updated_task.status,
            "new_priority": updated_task.priority,
        }
    
    return {"status": "no_changes", "task_id": task_id}


CREATE_KANBAN_TASK_DEF = {
    "type": "function",
    "function": {
        "name": "create_kanban_task",
        "description": _get_tool_desc(
            "create_kanban_task",
            "Create a new task in the Kanban board. Use this to delegate work to yourself or another agent. You may optionally schedule it for a future time or set a recurring cron expression."
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
                },
                "scheduled_at": {
                    "type": "string",
                    "description": "ISO 8601 datetime to delay the task until a specific future time (e.g., '2026-06-07T14:00:00Z').",
                },
                "cron_expression": {
                    "type": "string",
                    "description": "Standard cron expression for recurring tasks (e.g., '0 */6 * * *' for every 6 hours). Minimum interval is 5 minutes.",
                }
            },
            "required": ["title"],
        },
    },
}


LIST_KANBAN_TASKS_DEF = {
    "type": "function",
    "function": {
        "name": "list_kanban_tasks",
        "description": _get_tool_desc(
            "list_kanban_tasks",
            "Query the Kanban board for tasks based on status, assignee, or tags."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filter by status (e.g., 'inbox', 'doing', 'review', 'done', 'blocked')",
                },
                "assignee_id": {
                    "type": "string",
                    "description": "Filter by the ID of the agent assigned to the task",
                }
            },
        },
    },
}


UPDATE_KANBAN_TASK_DEF = {
    "type": "function",
    "function": {
        "name": "update_kanban_task",
        "description": _get_tool_desc(
            "update_kanban_task",
            "Update an existing Kanban task's status, priority, or append a comment/handoff note."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "ID of the task to update",
                },
                "new_status": {
                    "type": "string",
                    "description": "New status for the task",
                },
                "new_priority": {
                    "type": "integer",
                    "description": "New priority level (1=highest, 5=lowest)",
                },
                "comment": {
                    "type": "string",
                    "description": "Additional context, handoff note, or clarification to append to the task description",
                }
            },
            "required": ["task_id"],
        },
    },
}

