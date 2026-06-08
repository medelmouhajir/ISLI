import pytest
from unittest.mock import patch

@pytest.mark.asyncio
@patch("isli_skills.main.run_sandboxed_command")
async def test_shell_exec_api(mock_run, client):
    mock_run.return_value = {
        "stdout": "api test output",
        "stderr": "",
        "exit_code": 0,
        "duration_ms": 100,
        "timed_out": False
    }
    
    headers = {"X-Internal-Auth": "test-token"}
    payload = {
        "agent_id": "agent-1",
        "command": "echo hello",
        "timeout": 30
    }
    
    resp = await client.post("/exec", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["stdout"] == "api test output"
    assert data["exit_code"] == 0
    
    mock_run.assert_called_once_with(
        agent_id="agent-1",
        command="echo hello",
        timeout=30,
        working_dir=None
    )

@pytest.mark.asyncio
async def test_shell_exec_api_too_long(client):
    headers = {"X-Internal-Auth": "test-token"}
    payload = {
        "agent_id": "agent-1",
        "command": "a" * 5000,
    }
    
    resp = await client.post("/exec", json=payload, headers=headers)
    assert resp.status_code == 400
    assert "Command exceeds maximum length" in resp.json()["detail"]
