"""API tests for /v1/tasks endpoints."""

import pytest
from httpx import AsyncClient


class TestTasksAPI:
    @pytest.mark.asyncio
    async def test_create_task(self, client: AsyncClient):
        resp = await client.post("/v1/tasks", json={
            "title": "Test task",
            "created_by": "test-user",
            "type": "task",
            "priority": 2,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Test task"
        assert data["status"] == "inbox"
        assert data["priority"] == 2

    @pytest.mark.asyncio
    async def test_list_tasks(self, client: AsyncClient):
        resp = await client.get("/v1/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_move_task(self, client: AsyncClient):
        create = await client.post("/v1/tasks", json={
            "title": "Move me",
            "created_by": "test-user",
        })
        task_id = create.json()["id"]

        resp = await client.post(f"/v1/tasks/{task_id}/move?new_status=doing")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "doing"
        assert data["started_at"] is not None

    @pytest.mark.asyncio
    async def test_idempotency_key_rejection(self, client: AsyncClient):
        key = "unique-key-123"
        resp1 = await client.post("/v1/tasks", json={
            "title": "First",
            "created_by": "test-user",
            "idempotency_key": key,
        })
        assert resp1.status_code == 201

        resp2 = await client.post("/v1/tasks", json={
            "title": "Second",
            "created_by": "test-user",
            "idempotency_key": key,
        })
        assert resp2.status_code == 409

    @pytest.mark.asyncio
    async def test_max_depth_exceeded(self, client: AsyncClient):
        # Create parent at depth 3
        parent = await client.post("/v1/tasks", json={
            "title": "Depth 0",
            "created_by": "test-user",
        })
        p0 = parent.json()["id"]

        for i in range(3):
            child = await client.post("/v1/tasks", json={
                "title": f"Depth {i+1}",
                "created_by": "test-user",
                "parent_task_id": p0 if i == 0 else child.json()["id"],
            })
            p0 = child.json()["id"]

        # Depth 4 should fail
        resp = await client.post("/v1/tasks", json={
            "title": "Depth 4",
            "created_by": "test-user",
            "parent_task_id": p0,
        })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_task(self, client: AsyncClient):
        create = await client.post("/v1/tasks", json={
            "title": "Delete me",
            "created_by": "test-user",
        })
        task_id = create.json()["id"]
        resp = await client.delete(f"/v1/tasks/{task_id}")
        assert resp.status_code == 204
