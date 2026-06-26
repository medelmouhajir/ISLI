"""Regression tests for task work order assembly (greeting bug)."""

import pytest
from isli_agent import AgentConfig, AgentRunner
from isli_agent.runner.react_loop import ReActLoop


@pytest.fixture
def agent_config():
    return AgentConfig(
        id="test-agent",
        name="Local Name",
        description="Local Description",
        model_provider="ollama",
        model_id="qwen2.5:7b",
        skills=[],
    )


class TestBuildTaskWorkOrder:
    def test_input_wins_when_non_empty(self, agent_config):
        runner = AgentRunner(agent_config, "http://localhost:8000")
        loop = ReActLoop(runner)

        task_data = {
            "id": "task-1",
            "title": "Title",
            "description": "Description",
            "input": "Explicit work order",
        }
        assert loop._build_task_work_order(task_data) == "Explicit work order"

    def test_description_and_title_when_input_empty(self, agent_config):
        runner = AgentRunner(agent_config, "http://localhost:8000")
        loop = ReActLoop(runner)

        task_data = {
            "id": "task-2",
            "title": "Do the thing",
            "description": "Please write exactly TASK_RECEIVED_OK.",
            "input": "",
        }
        work_order = loop._build_task_work_order(task_data)
        assert work_order.startswith("Task: Do the thing")
        assert "Please write exactly TASK_RECEIVED_OK." in work_order

    def test_title_only_when_description_empty(self, agent_config):
        runner = AgentRunner(agent_config, "http://localhost:8000")
        loop = ReActLoop(runner)

        task_data = {
            "id": "task-3",
            "title": "Title only task",
            "description": "",
            "input": "",
        }
        assert loop._build_task_work_order(task_data) == "Task: Title only task"

    def test_description_only(self, agent_config):
        runner = AgentRunner(agent_config, "http://localhost:8000")
        loop = ReActLoop(runner)

        task_data = {
            "id": "task-4",
            "title": "",
            "description": "Description only work order",
            "input": "",
        }
        assert loop._build_task_work_order(task_data) == "Description only work order"

    def test_empty_task_data(self, agent_config):
        runner = AgentRunner(agent_config, "http://localhost:8000")
        loop = ReActLoop(runner)

        assert loop._build_task_work_order({"id": "task-5"}) == ""

    def test_duplicate_title_and_description_does_not_repeat(self, agent_config):
        runner = AgentRunner(agent_config, "http://localhost:8000")
        loop = ReActLoop(runner)

        task_data = {
            "id": "task-6",
            "title": "Same text",
            "description": "Same text",
            "input": "",
        }
        assert loop._build_task_work_order(task_data) == "Task: Same text"
