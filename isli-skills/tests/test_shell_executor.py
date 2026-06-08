import pytest
from unittest.mock import MagicMock, patch
from isli_skills.shell_executor import run_sandboxed_command, sanitize_working_dir
from fastapi import HTTPException

def test_sanitize_working_dir():
    assert sanitize_working_dir(None) == "."
    assert sanitize_working_dir("") == "."
    assert sanitize_working_dir(".") == "."
    assert sanitize_working_dir("src") == "src"
    
    with pytest.raises(ValueError):
        sanitize_working_dir("/etc")
    with pytest.raises(ValueError):
        sanitize_working_dir("../traversal")
    with pytest.raises(ValueError):
        sanitize_working_dir("c:\\windows")

@pytest.mark.asyncio
@patch("docker.from_env")
async def test_run_sandboxed_command_success(mock_from_env):
    mock_client = MagicMock()
    mock_from_env.return_value = mock_client
    
    mock_container = MagicMock()
    mock_client.containers.run.return_value = mock_container
    
    mock_container.wait.return_value = {"StatusCode": 0}
    mock_container.logs.return_value = b"hello world"
    
    result = await run_sandboxed_command("test-agent", "echo hello world")
    
    assert result["stdout"] == "hello world"
    assert result["exit_code"] == 0
    assert result["timed_out"] is False
    
    mock_client.containers.run.assert_called_once()
    mock_container.remove.assert_called_once()

@pytest.mark.asyncio
@patch("docker.from_env")
async def test_run_sandboxed_command_timeout(mock_from_env):
    mock_client = MagicMock()
    mock_from_env.return_value = mock_client
    
    mock_container = MagicMock()
    mock_client.containers.run.return_value = mock_container
    
    # Simulate timeout by raising exception in wait
    mock_container.wait.side_effect = Exception("Timeout")
    mock_container.logs.return_value = b"partial output"
    
    result = await run_sandboxed_command("test-agent", "sleep 10", timeout=1)
    
    assert result["stdout"] == "partial output"
    assert result["exit_code"] == -1
    assert result["timed_out"] is True
    assert "timed out" in result["error"].lower()
    
    mock_container.kill.assert_called_once()
    mock_container.remove.assert_called_once()
