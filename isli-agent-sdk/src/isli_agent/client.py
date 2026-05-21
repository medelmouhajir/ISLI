import httpx
import structlog
import json
from typing import Any, Optional
from .models import AgentConfig, Task, Checkpoint

logger = structlog.get_logger()

class CoreClient:
    """Client for interacting with the ISLI Core API."""
    
    def __init__(self, base_url: str, admin_key: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.admin_key = admin_key
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)
        self.token: Optional[str] = None

    def _get_headers(self, use_admin: bool = False) -> dict[str, str]:
        headers = {}
        if use_admin and self.admin_key:
            headers["Authorization"] = f"Bearer {self.admin_key}"
        elif self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def register(self, config: AgentConfig) -> dict[str, Any]:
        """Register the agent with Core API using admin key.

        Idempotent: works for new agents and already-registered agents.
        On 409 Conflict, recovers a fresh token via the admin token endpoint.
        """
        resp = await self.client.post(
            "/v1/agents",
            json=config.model_dump(),
            headers=self._get_headers(use_admin=True)
        )
        if resp.status_code == 409:
            # Agent exists — recover a fresh token using admin auth
            token_resp = await self.client.post(
                f"/v1/agents/{config.id}/token",
                headers=self._get_headers(use_admin=True)
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()
            self.token = token_data["token"]
            # Fetch existing agent config to return a consistent shape
            resp = await self.client.get(f"/v1/agents/{config.id}")
            resp.raise_for_status()
            data = resp.json()
            data["token"] = self.token
            return data

        resp.raise_for_status()
        data = resp.json()
        if "token" in data:
            self.token = data["token"]
        return data

    async def heartbeat(self, agent_id: str) -> str:
        """Send heartbeat and receive a renewed JWT token."""
        resp = await self.client.post(
            f"/v1/agents/{agent_id}/heartbeat",
            headers=self._get_headers()
        )
        resp.raise_for_status()
        data = resp.json()
        self.token = data["token"]
        return self.token

    async def get_task(self, task_id: str) -> Task:
        """Fetch full task details."""
        resp = await self.client.get(
            f"/v1/tasks/{task_id}",
            headers=self._get_headers()
        )
        resp.raise_for_status()
        return Task.model_validate(resp.json())

    async def get_context(self, agent_id: str, task_description: str, session_id: Optional[str] = None) -> str:
        """Fetch context injection from Keeper (via Core proxy)."""
        resp = await self.client.post(
            f"/v1/agents/{agent_id}/context",
            params={
                "task_description": task_description, 
                "session_id": session_id
            },
            headers=self._get_headers()
        )
        resp.raise_for_status()
        return resp.json().get("context_summary") or ""

    async def save_checkpoint(
        self, 
        task_id: str, 
        turn_number: int, 
        messages: list[dict[str, Any]], 
        tool_calls: Optional[list[dict[str, Any]]] = None
    ) -> dict[str, Any]:
        """Save agent turn state to Core API for resilience."""
        payload = {
            "turn_number": turn_number,
            "messages": messages,
            "tool_calls": tool_calls
        }
        resp = await self.client.post(
            f"/v1/tasks/{task_id}/checkpoint",
            json=payload,
            headers=self._get_headers(use_admin=True)
        )
        resp.raise_for_status()
        return resp.json()

    async def complete_task(self, task_id: str, output: str, status: str = "done") -> dict[str, Any]:
        """Update task with final output and move to a completion status."""
        # Update output first
        await self.client.put(
            f"/v1/tasks/{task_id}",
            json={"output": output},
            headers=self._get_headers(use_admin=True)
        )
        # Then move to final status
        resp = await self.client.post(
            f"/v1/tasks/{task_id}/move",
            params={"new_status": status},
            headers=self._get_headers(use_admin=True)
        )
        resp.raise_for_status()
        return resp.json()

    async def move_task(self, task_id: str, new_status: str) -> dict[str, Any]:
        """Move a task to a new status."""
        resp = await self.client.post(
            f"/v1/tasks/{task_id}/move",
            params={"new_status": new_status},
            headers=self._get_headers(use_admin=True)
        )
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        """Close the underlying HTTP client."""
        await self.client.aclose()

    async def get_session(self, session_id: str) -> dict[str, Any]:
        """Fetch session details."""
        resp = await self.client.get(
            f"/v1/sessions/{session_id}",
            headers=self._get_headers()
        )
        resp.raise_for_status()
        return resp.json()

    async def get_skills(self) -> list[dict[str, Any]]:
        """Fetch registered skill metadata from Core API."""
        resp = await self.client.get(
            "/v1/skills",
            headers=self._get_headers()
        )
        if resp.status_code != 200:
            logger.warning("client.get_skills_failed", status=resp.status_code)
            return []
        return resp.json()

    async def reply_to_session(self, session_id: str, text: str) -> dict[str, Any]:
        """Send a reply to a session (delivered to user via channels)."""
        resp = await self.client.post(
            f"/v1/sessions/{session_id}/reply",
            json={"text": text},
            headers=self._get_headers()
        )
        resp.raise_for_status()
        return resp.json()
