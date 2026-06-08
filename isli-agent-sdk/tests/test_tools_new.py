import pytest
import respx
from httpx import Response
from isli_agent.tools.kanban import create_kanban_task, list_kanban_tasks, update_kanban_task
from isli_agent.tools.engineering import create_engineering_plan
from isli_agent.client import CoreClient
from datetime import datetime, timezone


@pytest.fixture
def core_client():
    return CoreClient("http://localhost:8000", admin_key="test-admin-key")


class TestKanbanTools:
    @respx.mock
    async def test_create_kanban_task(self, core_client):
        route = respx.post("http://localhost:8000/v1/tasks").mock(
            return_value=Response(201, json={
                "id": "task-123",
                "title": "New Task",
                "status": "inbox",
                "agent_id": "agent-2",
                "input": ""
            })
        )
        
        result = await create_kanban_task(
            agent_id="agent-1",
            title="New Task",
            description="Task description",
            target_agent_id="agent-2",
            core_client=core_client
        )
        
        assert result["status"] == "inbox"
        assert result["task_id"] == "task-123"
        assert result["assigned_to"] == "agent-2"
        assert route.called
        
        body = route.calls.last.request.content.decode()
        assert '"title":"New Task"' in body
        assert '"created_by":"agent-1"' in body
        assert '"agent_id":"agent-2"' in body

    @respx.mock
    async def test_list_kanban_tasks(self, core_client):
        route = respx.get("http://localhost:8000/v1/tasks").mock(
            return_value=Response(200, json=[
                {
                    "id": "task-1",
                    "title": "Task 1",
                    "status": "doing",
                    "priority": 3,
                    "agent_id": "agent-1",
                    "input": "test input",
                    "created_at": "2026-06-07T12:00:00Z",
                    "tags": ["tag1"]
                }
            ])
        )
        
        result = await list_kanban_tasks(status="doing", core_client=core_client)
        
        assert len(result) == 1
        assert result[0]["id"] == "task-1"
        assert result[0]["status"] == "doing"
        assert route.called
        assert route.calls.last.request.url.params["status"] == "doing"

    @respx.mock
    async def test_update_kanban_task(self, core_client):
        # Mock get_task for comment appending
        get_route = respx.get("http://localhost:8000/v1/tasks/task-1").mock(
            return_value=Response(200, json={
                "id": "task-1",
                "title": "Task 1",
                "description": "Original description",
                "status": "doing",
                "priority": 3,
                "agent_id": "agent-1",
                "input": "test input"
            })
        )
        
        # Mock move_task
        move_route = respx.post("http://localhost:8000/v1/tasks/task-1/move").mock(
            return_value=Response(200, json={"status": "done"})
        )
        
        # Mock update_task
        update_route = respx.put("http://localhost:8000/v1/tasks/task-1").mock(
            return_value=Response(200, json={
                "id": "task-1",
                "title": "Task 1",
                "status": "done",
                "priority": 1,
                "input": "test input",
                "description": "Original description\n\n--- Handoff/Comment... ---"
            })
        )
        
        result = await update_kanban_task(
            task_id="task-1",
            new_status="done",
            new_priority=1,
            comment="Finished work",
            core_client=core_client
        )
        
        assert result["status"] == "updated"
        assert result["new_status"] == "done"
        assert result["new_priority"] == 1
        assert get_route.called
        assert move_route.called
        assert update_route.called
        
        # Verify comment was appended in update call
        update_body = update_route.calls.last.request.content.decode()
        assert "Finished work" in update_body
        assert "Original description" in update_body


class TestEngineeringTools:
    @respx.mock
    async def test_create_engineering_plan(self, core_client):
        # Engineering plan calls file_write
        route = respx.post("http://localhost:8000/v1/skills/file-write/write").mock(
            return_value=Response(200, json={"status": "written", "size_bytes": 100})
        )
        
        result = await create_engineering_plan(
            agent_id="agent-1",
            objective="Build a feature",
            steps=["Step 1", "Step 2"],
            core_client=core_client
        )
        
        assert result["status"] == "plan_created"
        assert result["filename"] == "PLAN.md"
        assert result["step_count"] == 2
        assert "Implementation Plan: Build a feature" in result["preview"]
        assert route.called
        
        body = route.calls.last.request.content.decode()
        assert '"path":"PLAN.md"' in body
        assert "# Implementation Plan: Build a feature" in body
        assert "1. Step 1" in body
        assert "2. Step 2" in body
