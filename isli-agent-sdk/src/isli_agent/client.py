import httpx
import structlog
from typing import Any, Optional
from .models import AgentConfig, Task

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
        else:
            resp.raise_for_status()
            data = resp.json()
            if "token" in data:
                self.token = data["token"]

        # Fetch full config (with resolved api_key) using admin auth
        config_resp = await self.client.get(
            f"/v1/agents/{config.id}/config",
            headers=self._get_headers(use_admin=True)
        )
        config_resp.raise_for_status()
        final_data = config_resp.json()
        final_data["token"] = self.token
        return final_data

    async def recover_token(self, agent_id: str) -> str:
        """Recover a fresh token via admin auth when the current token is revoked."""
        resp = await self.client.post(
            f"/v1/agents/{agent_id}/token",
            headers=self._get_headers(use_admin=True)
        )
        resp.raise_for_status()
        token_data = resp.json()
        self.token = token_data["token"]
        return self.token

    async def create_task(self, payload: dict[str, Any]) -> Task:
        """Create a new task in the Kanban board."""
        resp = await self.client.post(
            "/v1/tasks",
            json=payload,
            headers=self._get_headers(use_admin=True)
        )
        resp.raise_for_status()
        return Task.model_validate(resp.json())

    async def list_tasks(self, status: Optional[str] = None, agent_id: Optional[str] = None) -> list[Task]:
        """List tasks from the Kanban board."""
        params = {}
        if status:
            params["status"] = status
        if agent_id:
            params["agent_id"] = agent_id
        
        resp = await self.client.get(
            "/v1/tasks",
            params=params,
            headers=self._get_headers(use_admin=True)
        )
        resp.raise_for_status()
        return [Task.model_validate(t) for t in resp.json()]

    async def update_task(self, task_id: str, payload: dict[str, Any]) -> Task:
        """Update an existing task in the Kanban board."""
        resp = await self.client.put(
            f"/v1/tasks/{task_id}",
            json=payload,
            headers=self._get_headers(use_admin=True)
        )
        resp.raise_for_status()
        return Task.model_validate(resp.json())

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
        """Fetch context injection from Keeper (via Core proxy).

        .. deprecated::
            Context is now delivered inline via WebSocket ``task:updated`` events.
            This method is kept for backward compatibility but should not be called
            from new code.
        """
        import warnings
        warnings.warn(
            "get_context() is deprecated; context_summary is delivered inline via WebSocket",
            DeprecationWarning,
            stacklevel=2,
        )
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

    async def update_session_status(self, session_id: str, status: str) -> dict[str, Any]:
        """Explicitly update session status (e.g. ready after agent finishes processing)."""
        resp = await self.client.post(
            f"/v1/sessions/{session_id}/status",
            json={"status": status},
            headers=self._get_headers()
        )
        resp.raise_for_status()
        return resp.json()

    async def reply_to_session(
        self,
        session_id: str,
        text: str,
        components: list[dict[str, Any]] | None = None,
        audio_b64: str | None = None,
        audio_voice: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Send a reply to a session (delivered to user via channels).

        If audio_b64 is provided, Core will forward it as a voice message
        alongside the text reply. If attachments are provided, each must be a
        dict with 'path' and optional 'workspace_id' and 'caption'.
        """
        payload: dict[str, Any] = {"text": text}
        if components:
            payload["components"] = components
        if audio_b64:
            payload["audio_b64"] = audio_b64
        if audio_voice:
            payload["audio_voice"] = audio_voice
        if attachments:
            payload["attachments"] = attachments
        resp = await self.client.post(
            f"/v1/sessions/{session_id}/reply",
            json=payload,
            headers=self._get_headers()
        )
        resp.raise_for_status()
        return resp.json()

    async def report_usage(self, agent_id: str, usage: dict[str, Any]) -> dict[str, Any]:
        """Report token usage back to Core for cost ledger and budget enforcement."""
        resp = await self.client.post(
            f"/v1/agents/{agent_id}/usage",
            json=usage,
            headers=self._get_headers()
        )
        resp.raise_for_status()
        return resp.json()

    async def report_model_error(self, agent_id: str, category: str, reason: str | None = None) -> dict[str, Any]:
        """Report a model error to Core so the agent can be flagged in the Board UI."""
        resp = await self.client.post(
            f"/v1/agents/{agent_id}/model_error",
            json={"category": category, "reason": reason},
            headers=self._get_headers()
        )
        resp.raise_for_status()
        return resp.json()

    async def report_model_recovery(self, agent_id: str) -> dict[str, Any]:
        """Report that the agent has recovered from a model error."""
        resp = await self.client.post(
            f"/v1/agents/{agent_id}/model_recovery",
            headers=self._get_headers()
        )
        resp.raise_for_status()
        return resp.json()

    async def invoke_skill(self, skill_name: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Call a skill through the Core proxy."""
        resp = await self.client.post(
            f"/v1/skills/{skill_name}/{action}",
            json=payload,
            headers=self._get_headers()
        )
        resp.raise_for_status()
        return resp.json()
