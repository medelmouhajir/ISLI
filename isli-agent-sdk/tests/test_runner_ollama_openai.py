import os

from isli_agent.models import AgentConfig
from isli_agent.runner import AgentRunner, OLLAMA_OPENAI_BASE, OLLAMA_NATIVE_OPT_OUT_KEY


def _make_config(model_provider="ollama", model_id="kimi-k2.7-code", api_base=None, config=None):
    return AgentConfig(
        id="donna",
        name="Donna",
        description="Test agent",
        model_provider=model_provider,
        model_id=model_id,
        api_key="test-key",
        api_base=api_base,
        config=config or {},
    )


def _make_runner(config):
    runner = AgentRunner.__new__(AgentRunner)
    runner.config = config
    runner._model_circuit_open = False
    return runner


class TestOllamaOpenAiEndpointRemapping:
    """Ollama Cloud agents should default to the OpenAI-compatible /v1 endpoint."""

    def test_resolve_model_maps_ollama_to_openai(self):
        runner = _make_runner(_make_config())
        assert runner._resolve_model() == "openai/kimi-k2.7-code"

    def test_resolve_model_respects_routed_model(self):
        runner = _make_runner(_make_config())
        assert runner._resolve_model({"provider": "ollama", "model_id": "kimi-k2.6"}) == "openai/kimi-k2.6"

    def test_resolve_model_keeps_non_ollama_provider(self):
        runner = _make_runner(_make_config(model_provider="openai"))
        assert runner._resolve_model() == "openai/kimi-k2.7-code"

    def test_resolve_model_allows_native_opt_out(self):
        runner = _make_runner(_make_config(config={OLLAMA_NATIVE_OPT_OUT_KEY: True}))
        assert runner._resolve_model() == "ollama/kimi-k2.7-code"

    def test_apply_auth_defaults_api_base_for_ollama(self):
        runner = _make_runner(_make_config())
        kwargs = {}
        runner._apply_auth_to_kwargs(kwargs)
        assert kwargs["api_base"] == OLLAMA_OPENAI_BASE

    def test_apply_auth_respects_explicit_api_base(self):
        runner = _make_runner(_make_config(api_base="http://localhost:11434"))
        kwargs = {}
        runner._apply_auth_to_kwargs(kwargs)
        assert kwargs["api_base"] == "http://localhost:11434"

    def test_apply_auth_sets_openai_api_key_for_ollama(self):
        runner = _make_runner(_make_config())
        runner._apply_auth_to_kwargs({})
        assert os.environ["OPENAI_API_KEY"] == "test-key"
        assert os.environ["OLLAMA_API_KEY"] == "test-key"

    def test_apply_auth_native_opt_out_keeps_ollama_env(self):
        runner = _make_runner(_make_config(config={OLLAMA_NATIVE_OPT_OUT_KEY: True}))
        runner._apply_auth_to_kwargs({})
        assert os.environ["OLLAMA_API_KEY"] == "test-key"


class TestEmptyFinalResponseFallback:
    """If the model returns an empty final response after using tools, synthesize one."""

    def test_fallback_summary_single_tool_result(self):
        runner = _make_runner(_make_config())
        messages = [
            {"role": "tool", "tool_call_id": "1", "name": "file_list", "content": "plan.md, todo.txt"},
        ]
        summary = runner._build_tool_fallback_summary(messages)
        assert "checked the relevant source" in summary
        assert "plan.md" in summary

    def test_fallback_summary_multiple_tool_results(self):
        runner = _make_runner(_make_config())
        messages = [
            {"role": "tool", "tool_call_id": "1", "name": "file_list", "content": "plan.md"},
            {"role": "tool", "tool_call_id": "2", "name": "list_kanban_tasks", "content": "[{'id': 'x'}]"},
        ]
        summary = runner._build_tool_fallback_summary(messages)
        assert "gathered the following information" in summary
        assert "plan.md" in summary
        assert "x" in summary

    def test_fallback_summary_ignores_errors(self):
        runner = _make_runner(_make_config())
        messages = [
            {"role": "tool", "tool_call_id": "1", "name": "file_list", "content": "Error: workspace unreachable"},
        ]
        summary = runner._build_tool_fallback_summary(messages)
        assert "didn't generate a final response" in summary

    def test_fallback_summary_truncates_long_results(self):
        runner = _make_runner(_make_config())
        long_content = "x" * 500
        messages = [
            {"role": "tool", "tool_call_id": "1", "name": "file_read", "content": long_content},
        ]
        summary = runner._build_tool_fallback_summary(messages)
        assert "..." in summary
        assert len(summary) < len(long_content) + 100

    def test_fallback_summary_no_tools(self):
        runner = _make_runner(_make_config())
        summary = runner._build_tool_fallback_summary([])
        assert "didn't generate a final response" in summary
