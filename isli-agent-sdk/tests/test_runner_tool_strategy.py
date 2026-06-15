import pytest
from isli_agent import AgentConfig, AgentRunner


@pytest.fixture
def base_config():
    return AgentConfig(
        id="test-agent",
        name="Test Agent",
        model_provider="ollama",
        model_id="qwen2.5:7b",
        skills=[],
    )


def _make_runner_with_tools(config: AgentConfig) -> AgentRunner:
    runner = AgentRunner(config, "http://localhost:8000")
    runner.add_tool("file_read", lambda: "ok", {
        "type": "function",
        "function": {"name": "file_read", "description": "Read a file"},
        "x_isli_skill": "file-read",
    })
    runner.add_tool("web_fetch", lambda: "ok", {
        "type": "function",
        "function": {"name": "web_fetch", "description": "Fetch a URL"},
        "x_isli_skill": "web-fetch",
    })
    runner.add_tool("send_message", lambda: "ok", {
        "type": "function",
        "function": {"name": "send_message", "description": "Send a message"},
        "x_isli_skill": "send-message",
    })
    runner.add_tool("get_current_datetime", lambda: "ok", {
        "type": "function",
        "function": {"name": "get_current_datetime", "description": "Get time"},
        "x_isli_always_active": True,
    })
    runner.add_tool("discover_skills", lambda: "ok", {
        "type": "function",
        "function": {"name": "discover_skills", "description": "Discover skills"},
    })
    # Snapshot full set exactly as _sync_config does
    runner._all_tool_definitions = list(runner.tool_definitions)
    return runner


class TestToolInjectionStrategy:
    def test_auto_with_relevant_skills_filters(self, base_config):
        base_config.config = {"tool_injection_strategy": "auto"}
        runner = _make_runner_with_tools(base_config)

        result = runner._filter_tools_by_relevance(["file-read"])
        names = {d["function"]["name"] for d in result}

        assert "file_read" in names
        assert "get_current_datetime" in names  # always_active
        assert "web_fetch" not in names
        assert "send_message" not in names

    def test_auto_empty_skills_falls_back_to_all(self, base_config):
        base_config.config = {"tool_injection_strategy": "auto"}
        runner = _make_runner_with_tools(base_config)

        result = runner._filter_tools_by_relevance([])
        names = {d["function"]["name"] for d in result}

        assert names == {
            "file_read",
            "web_fetch",
            "send_message",
            "get_current_datetime",
            "discover_skills",
        }

    def test_auto_none_skills_falls_back_to_all(self, base_config):
        base_config.config = {"tool_injection_strategy": "auto"}
        runner = _make_runner_with_tools(base_config)

        result = runner._filter_tools_by_relevance(None)
        names = {d["function"]["name"] for d in result}

        assert names == {
            "file_read",
            "web_fetch",
            "send_message",
            "get_current_datetime",
            "discover_skills",
        }

    def test_all_strategy_ignores_relevant_skills(self, base_config):
        base_config.config = {"tool_injection_strategy": "all"}
        runner = _make_runner_with_tools(base_config)

        result = runner._filter_tools_by_relevance(["file-read"])
        names = {d["function"]["name"] for d in result}

        assert names == {
            "file_read",
            "web_fetch",
            "send_message",
            "get_current_datetime",
            "discover_skills",
        }

    def test_all_strategy_empty_skills_returns_all(self, base_config):
        base_config.config = {"tool_injection_strategy": "all"}
        runner = _make_runner_with_tools(base_config)

        result = runner._filter_tools_by_relevance([])
        names = {d["function"]["name"] for d in result}

        assert names == {
            "file_read",
            "web_fetch",
            "send_message",
            "get_current_datetime",
            "discover_skills",
        }

    def test_strict_with_relevant_skills_filters(self, base_config):
        base_config.config = {"tool_injection_strategy": "strict"}
        runner = _make_runner_with_tools(base_config)

        result = runner._filter_tools_by_relevance(["file-read"])
        names = {d["function"]["name"] for d in result}

        assert "file_read" in names
        assert "get_current_datetime" in names  # always_active
        assert "web_fetch" not in names
        assert "send_message" not in names
        assert "discover_skills" not in names

    def test_strict_empty_skills_returns_only_always_active(self, base_config):
        base_config.config = {"tool_injection_strategy": "strict"}
        runner = _make_runner_with_tools(base_config)

        result = runner._filter_tools_by_relevance([])
        names = {d["function"]["name"] for d in result}

        assert names == {"get_current_datetime"}

    def test_strict_none_skills_returns_only_always_active(self, base_config):
        base_config.config = {"tool_injection_strategy": "strict"}
        runner = _make_runner_with_tools(base_config)

        result = runner._filter_tools_by_relevance(None)
        names = {d["function"]["name"] for d in result}

        assert names == {"get_current_datetime"}

    def test_default_without_config_key_uses_auto(self, base_config):
        # config is empty, so tool_injection_strategy defaults to "auto"
        runner = _make_runner_with_tools(base_config)

        result = runner._filter_tools_by_relevance(None)
        names = {d["function"]["name"] for d in result}

        assert names == {
            "file_read",
            "web_fetch",
            "send_message",
            "get_current_datetime",
            "discover_skills",
        }
