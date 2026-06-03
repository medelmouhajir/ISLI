import json
import pytest
from isli_agent.runner import AgentRunner, _ParsedToolCall, _ParsedFunction


def _make_runner_with_tools():
    """Create a runner with a few registered tools for JSON extraction tests."""
    runner = AgentRunner.__new__(AgentRunner)
    runner.tools = {}
    runner.tool_definitions = []
    runner.add_tool("ui_components", lambda **kw: kw, {
        "type": "function",
        "function": {"name": "ui_components", "description": "Render UI"},
    })
    runner.add_tool("file_read", lambda **kw: kw, {
        "type": "function",
        "function": {"name": "file_read", "description": "Read file"},
    })
    return runner


class MockMessage:
    """Minimal stand-in for a LiteLLM/OpenAI message object."""

    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self, exclude_none=True):
        result = {}
        if self.content is not None:
            result["content"] = self.content
        if self.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in self.tool_calls
            ]
        return result


class TestXmlToolCallParsing:
    """Test the Anthropic-style XML fallback parser in AgentRunner."""

    def test_no_xml_returns_empty(self):
        runner = AgentRunner.__new__(AgentRunner)
        result = runner._extract_xml_tool_calls("Just some plain text.")
        assert result == []

    def test_well_formed_single_invoke(self):
        runner = AgentRunner.__new__(AgentRunner)
        content = """
        Certainly. Here is your card.
        <function_calls>
          <invoke name="ui_components">
            <arg name="component_type">card</arg>
            <arg name="props">{"title":"Demo"}</arg>
            <arg name="action_id">demo_001</arg>
          </invoke>
        </function_calls>
        """
        result = runner._extract_xml_tool_calls(content)

        assert len(result) == 1
        assert result[0].id == "xml_call_0"
        assert result[0].type == "function"
        assert result[0].function.name == "ui_components"

        args = json.loads(result[0].function.arguments)
        assert args["component_type"] == "card"
        assert args["action_id"] == "demo_001"
        assert args["props"] == {"title": "Demo"}

    def test_multiple_invokes(self):
        runner = AgentRunner.__new__(AgentRunner)
        content = """
        <function_calls>
          <invoke name="file_read">
            <arg name="path">/tmp/a.txt</arg>
          </invoke>
          <invoke name="file_write">
            <arg name="path">/tmp/b.txt</arg>
            <arg name="content">hello</arg>
          </invoke>
        </function_calls>
        """
        result = runner._extract_xml_tool_calls(content)

        assert len(result) == 2
        assert result[0].id == "xml_call_0"
        assert result[0].function.name == "file_read"
        assert result[1].id == "xml_call_1"
        assert result[1].function.name == "file_write"

        args0 = json.loads(result[0].function.arguments)
        assert args0["path"] == "/tmp/a.txt"

        args1 = json.loads(result[1].function.arguments)
        assert args1["path"] == "/tmp/b.txt"
        assert args1["content"] == "hello"

    def test_json_array_and_numeric_args(self):
        runner = AgentRunner.__new__(AgentRunner)
        content = """
        <function_calls>
          <invoke name="web_search">
            <arg name="queries">["q1", "q2"]</arg>
            <arg name="limit">5</arg>
            <arg name="deep">true</arg>
          </invoke>
        </function_calls>
        """
        result = runner._extract_xml_tool_calls(content)

        args = json.loads(result[0].function.arguments)
        assert args["queries"] == ["q1", "q2"]
        assert args["limit"] == 5
        assert args["deep"] is True

    def test_malformed_xml_returns_empty(self):
        runner = AgentRunner.__new__(AgentRunner)
        content = "<function_calls><invoke name=\"x\"><arg>broken</function_calls>"
        result = runner._extract_xml_tool_calls(content)
        assert result == []

    def test_extract_tool_calls_prefers_openai(self):
        runner = AgentRunner.__new__(AgentRunner)
        openai_calls = [_ParsedToolCall("call_abc", "file_read", '{"path":"/x"}')]
        msg = MockMessage(
            content="<function_calls><invoke name=\"ui_components\">...</invoke></function_calls>",
            tool_calls=openai_calls,
        )
        result = runner._extract_tool_calls(msg)
        assert result is openai_calls

    def test_extract_tool_calls_falls_back_to_xml(self):
        runner = AgentRunner.__new__(AgentRunner)
        content = """
        <function_calls>
          <invoke name="ui_components">
            <arg name="component_type">card</arg>
          </invoke>
        </function_calls>
        """
        msg = MockMessage(content=content, tool_calls=None)
        result = runner._extract_tool_calls(msg)

        assert len(result) == 1
        assert result[0].function.name == "ui_components"

    def test_strip_xml_tool_calls(self):
        content = (
            "Here is a card for you.\n"
            "<function_calls>\n"
            "  <invoke name=\"ui_components\">\n"
            "    <arg name=\"component_type\">card</arg>\n"
            "  </invoke>\n"
            "</function_calls>\n"
            "Let me know if you need more."
        )
        stripped = AgentRunner._strip_xml_tool_calls(content)
        assert "<function_calls>" not in stripped
        assert "</invoke>" not in stripped
        assert "Here is a card for you." in stripped
        assert "Let me know if you need more." in stripped

    def test_strip_xml_no_match_returns_unchanged(self):
        content = "No XML here at all."
        stripped = AgentRunner._strip_xml_tool_calls(content)
        assert stripped == "No XML here at all."

    def test_multiple_function_calls_blocks(self):
        runner = AgentRunner.__new__(AgentRunner)
        content = """
        <function_calls>
          <invoke name="a">
            <arg name="x">1</arg>
          </invoke>
        </function_calls>
        Some text.
        <function_calls>
          <invoke name="b">
            <arg name="y">2</arg>
          </invoke>
        </function_calls>
        """
        result = runner._extract_xml_tool_calls(content)
        assert len(result) == 2
        assert result[0].function.name == "a"
        assert result[1].function.name == "b"
        assert result[0].id == "xml_call_0"
        assert result[1].id == "xml_call_1"


class TestJsonToolCallParsing:
    """Test the JSON-in-text fallback parser in AgentRunner."""

    def test_no_json_returns_empty(self):
        runner = _make_runner_with_tools()
        result = runner._extract_json_tool_calls("Just some plain text.")
        assert result == []

    def test_json_tool_call_extracted(self):
        runner = _make_runner_with_tools()
        content = (
            'I\'ll render a card for you. '
            '{"name":"ui_components","arguments":{"component_type":"card","action_id":"demo"}}'
        )
        result = runner._extract_json_tool_calls(content)

        assert len(result) == 1
        assert result[0].id == "json_call_0"
        assert result[0].function.name == "ui_components"

        args = json.loads(result[0].function.arguments)
        assert args["component_type"] == "card"
        assert args["action_id"] == "demo"

    def test_json_unregistered_tool_ignored(self):
        runner = _make_runner_with_tools()
        content = '{"name":"unknown_tool","arguments":{"x":1}}'
        result = runner._extract_json_tool_calls(content)
        assert result == []

    def test_json_nested_args(self):
        runner = _make_runner_with_tools()
        content = (
            '{"name":"ui_components","arguments":'
            '{"component_type":"card","props":{"title":"T","fields":[]},'
            '"buttons":[{"label":"OK","action_type":"ok","payload":{}}]}}'
        )
        result = runner._extract_json_tool_calls(content)

        assert len(result) == 1
        args = json.loads(result[0].function.arguments)
        assert args["component_type"] == "card"
        assert args["props"]["title"] == "T"
        assert args["buttons"][0]["label"] == "OK"

    def test_json_multiple_blobs(self):
        runner = _make_runner_with_tools()
        content = (
            'Here you go: {"name":"file_read","arguments":{"path":"/a"}} '
            'and {"name":"ui_components","arguments":{"component_type":"card"}}'
        )
        result = runner._extract_json_tool_calls(content)
        assert len(result) == 2
        assert result[0].function.name == "file_read"
        assert result[1].function.name == "ui_components"

    def test_json_not_tool_call_ignored(self):
        runner = _make_runner_with_tools()
        content = '{"user":"alice","message":"hello"}'
        result = runner._extract_json_tool_calls(content)
        assert result == []

    def test_extract_tool_calls_prefers_json_over_xml(self):
        """When no OpenAI tool_calls, XML is tried first, then JSON."""
        runner = _make_runner_with_tools()
        content = (
            '<function_calls><invoke name="ui_components">'
            '<arg name="component_type">card</arg></invoke></function_calls>'
        )
        msg = MockMessage(content=content, tool_calls=None)
        result = runner._extract_tool_calls(msg)
        assert len(result) == 1
        assert result[0].function.name == "ui_components"

    def test_extract_tool_calls_falls_back_to_json(self):
        runner = _make_runner_with_tools()
        content = (
            '{"name":"ui_components","arguments":{"component_type":"card"}}'
        )
        msg = MockMessage(content=content, tool_calls=None)
        result = runner._extract_tool_calls(msg)
        assert len(result) == 1
        assert result[0].function.name == "ui_components"

    def test_strip_json_tool_calls(self):
        runner = _make_runner_with_tools()
        content = (
            "Here is a card for you. "
            '{"name":"ui_components","arguments":{"component_type":"card"}}'
        )
        stripped = runner._strip_json_tool_calls(content)
        assert "ui_components" not in stripped
        assert "component_type" not in stripped
        assert "Here is a card for you." in stripped

    def test_strip_tool_calls_unified(self):
        runner = _make_runner_with_tools()
        content = (
            "Before. "
            '<function_calls><invoke name="ui_components">'
            '<arg name="component_type">card</arg></invoke></function_calls>'
            " Middle. "
            '{"name":"file_read","arguments":{"path":"/x"}}'
            " After."
        )
        stripped = runner._strip_tool_calls(content)
        assert stripped == "Before.  Middle.  After."

    def test_malformed_json_ignored(self):
        runner = _make_runner_with_tools()
        content = '{"name":"ui_components","arguments":{broken}'
        result = runner._extract_json_tool_calls(content)
        assert result == []
