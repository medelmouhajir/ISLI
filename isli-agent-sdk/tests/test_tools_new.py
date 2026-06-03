import pytest
import respx
from httpx import Response
from isli_agent.tools.kanban import create_kanban_task
from isli_agent.tools.engineering import create_engineering_plan
from isli_agent.client import CoreClient


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
