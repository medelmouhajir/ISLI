import pytest
import respx
from httpx import Response
from isli_agent import AgentConfig, AgentRunner

@pytest.fixture
def agent_config():
    return AgentConfig(
        id="test-agent",
        name="Local Name",
        description="Local Description",
        model_provider="ollama",
        model_id="qwen2.5:7b",
        skills=[], # Start with no skills locally
    )

class TestAgentRunnerSync:
    @respx.mock
    async def test_startup_syncs_config_and_skills(self, agent_config):
        # 1. Mock registration response with DIFFERENT data (the "database" version)
        respx.post("http://localhost:8000/v1/agents").mock(
            return_value=Response(200, json={
                "id": "test-agent",
                "name": "Database Name",
                "description": "Database Description",
                "persona": "Database Persona",
                "skills": ["file-read", "web-fetch"],
                "status": "online",
                "model_provider": "ollama",
                "model_id": "qwen2.5:7b",
                "channels": [],
                "config": {"debug": True},
                "token_used": 0,
                "max_retries": 3,
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "token": "fake-token"
            })
        )
        
        # 2. Mock skills discovery
        respx.get("http://localhost:8000/v1/skills").mock(
            return_value=Response(200, json=[
                {"name": "file-read", "description": "Read files", "type": "external"},
                {"name": "web-fetch", "description": "Fetch web", "type": "external"}
            ])
        )
        
        # 3. Mock config fetch (register() pulls full config after POST /v1/agents)
        respx.get("http://localhost:8000/v1/agents/test-agent/config").mock(
            return_value=Response(200, json={
                "id": "test-agent",
                "name": "Database Name",
                "description": "Database Description",
                "persona": "Database Persona",
                "skills": ["file-read", "web-fetch"],
                "status": "online",
                "model_provider": "ollama",
                "model_id": "qwen2.5:7b",
                "channels": [],
                "config": {"debug": True},
            })
        )

        # 4. Mock heartbeat and websocket (to avoid hanging)
        respx.post("http://localhost:8000/v1/agents/test-agent/heartbeat").mock(
            return_value=Response(200, json={"token": "new-token"})
        )
        
        runner = AgentRunner(agent_config, "http://localhost:8000")
        
        # We'll monkeypatch _ws_loop to avoid actual connection
        async def mock_ws_loop():
            pass
        runner._ws_loop = mock_ws_loop
        
        await runner.start()
        
        # Verify config was synced
        assert runner.config.name == "Database Name"
        assert runner.config.description == "Database Description"
        assert runner.config.persona == "Database Persona"
        assert runner.config.skills == ["file-read", "web-fetch"]
        assert runner.config.config["debug"] is True
        
        # Verify tools were registered based on SYNCED skills
        assert "file_read" in runner.tools
        assert "web_fetch" in runner.tools
        assert "get_current_datetime" in runner.tools # System tool always there

    def test_assemble_system_prompt_includes_tools(self, agent_config):
        runner = AgentRunner(agent_config, "http://localhost:8000")

        # Manually register a tool
        runner.add_tool("test_tool", lambda: "ok", {
            "type": "function",
            "function": {
                "name": "test_tool",
                "description": "A test tool description"
            }
        })

        prompt = runner._assemble_system_prompt("Context Summary")

        assert "=== IDENTITY ===" in prompt
        assert "Local Name" in prompt
        assert "=== AVAILABLE TOOLS ===" in prompt
        assert "- test_tool: A test tool description" in prompt
        assert "Context Summary" in prompt
        assert "Call them when appropriate" in prompt

    def test_assemble_system_prompt_includes_task_block_in_task_mode(self, agent_config):
        runner = AgentRunner(agent_config, "http://localhost:8000")

        prompt = runner._assemble_system_prompt("Task context", task_mode=True)

        assert "## Kanban Task Execution Rules" in prompt
        assert "You are currently executing an assigned Kanban task" in prompt
        assert "NEVER render a greeting card" in prompt
        assert "MUST call file-write" in prompt
        assert "=== IDENTITY ===" in prompt  # base template still present

    def test_assemble_system_prompt_omits_task_block_in_chat_mode(self, agent_config):
        runner = AgentRunner(agent_config, "http://localhost:8000")

        prompt = runner._assemble_system_prompt("Chat context", task_mode=False)

        assert "## Kanban Task Execution Rules" not in prompt
        assert "You are currently executing an assigned Kanban task" not in prompt
