"""Tool-call parsing for native OpenAI, Anthropic XML, JSON-in-text, and legacy markup."""

import json
import re
import xml.etree.ElementTree as ET
from typing import Any, Callable, Dict

import structlog

logger = structlog.get_logger()


class _ParsedFunction:
    """Minimal stand-in for OpenAI function object inside a tool call."""

    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class _ParsedToolCall:
    """Minimal stand-in for OpenAI tool_call object extracted from XML."""

    def __init__(self, id: str, name: str, arguments: str):
        self.id = id
        self.type = "function"
        self.function = _ParsedFunction(name, arguments)


def extract_xml_tool_calls(content: str) -> list[_ParsedToolCall]:
    """Parse Anthropic-style XML function calls from message content.

    Supports blocks like:
        <function_calls>
          <invoke name="tool_name">
            <arg name="key">value</arg>
          </invoke>
        </function_calls>

    Returns a list of _ParsedToolCall objects that mimic OpenAI's
    tool_call interface so the existing execution loop works unchanged.
    """
    if "<function_calls>" not in content:
        return []

    parsed: list[_ParsedToolCall] = []
    try:
        # Extract every <function_calls> block (non-greedy, multi-line)
        blocks = re.findall(
            r"<function_calls>(.*?)</function_calls>", content, flags=re.DOTALL
        )
        call_index = 0
        for block in blocks:
            root = ET.fromstring(f"<function_calls>{block}</function_calls>")
            for invoke in root.findall("invoke"):
                tool_name = invoke.get("name")
                if not tool_name:
                    continue

                args: dict[str, Any] = {}
                for arg in invoke.findall("arg"):
                    arg_name = arg.get("name")
                    if not arg_name:
                        continue
                    raw_value = arg.text or ""
                    # Try JSON decode for structured values (dicts, lists, numbers, booleans)
                    try:
                        args[arg_name] = json.loads(raw_value)
                    except json.JSONDecodeError:
                        args[arg_name] = raw_value

                parsed.append(
                    _ParsedToolCall(
                        id=f"xml_call_{call_index}",
                        name=tool_name,
                        arguments=json.dumps(args),
                    )
                )
                call_index += 1
    except Exception as exc:
        logger.warning("runner.xml_parse_failed", error=str(exc))

    return parsed


def extract_json_tool_calls(content: str, tools: Dict[str, Callable]) -> list[_ParsedToolCall]:
    """Parse JSON tool call blobs embedded in message text.

    Handles models that output raw JSON like:
        {"name":"ui_components","arguments":{"component_type":"card",...}}
    """
    if "{" not in content:
        return []

    # Find top-level JSON object substrings via brace matching
    def _find_json_objects(text: str) -> list[str]:
        objects: list[str] = []
        depth = 0
        start: int | None = None
        for i, ch in enumerate(text):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start is not None:
                    objects.append(text[start : i + 1])
                    start = None
        return objects

    parsed: list[_ParsedToolCall] = []
    for obj_str in _find_json_objects(content):
        try:
            blob = json.loads(obj_str)
        except (json.JSONDecodeError, ValueError):
            continue
        if (
            isinstance(blob, dict)
            and "name" in blob
            and "arguments" in blob
            and isinstance(blob["arguments"], dict)
            and blob["name"] in tools
        ):
            parsed.append(
                _ParsedToolCall(
                    id=f"json_call_{len(parsed)}",
                    name=blob["name"],
                    arguments=json.dumps(blob["arguments"]),
                )
            )

    return parsed


def extract_legacy_tool_calls(content: str, tools: Dict[str, Callable]) -> list[_ParsedToolCall]:
    """Parse <tool_call> blocks emitted by models that do not support native tool calling.

    Supports blocks like:
        <tool_call>
          <function=tool_name>
            <parameter=arg_name>value</parameter>
          </function>
        </tool_call>

    Also handles the attribute-style variant:
        <function name="tool_name">
          <parameter name="arg_name">value</parameter>
        </function>

    Returns a list of _ParsedToolCall objects that mimic OpenAI's
    tool_call interface so the existing execution loop works unchanged.
    """
    if "<tool_call>" not in content:
        return []

    parsed: list[_ParsedToolCall] = []
    # Extract every <tool_call> block (non-greedy, multi-line)
    blocks = re.findall(r"<tool_call>(.*?)</tool_call>", content, flags=re.DOTALL)
    call_index = 0
    for block in blocks:
        # Extract function name: <function=NAME> or <function name="NAME">
        func_match = re.search(r"<function\s*=\s*([^\>>\s'\"]+)", block)
        if not func_match:
            func_match = re.search(r'<function\s+name\s*=\s*["\']([^"\']+)["\']', block)
        if not func_match:
            continue
        tool_name = func_match.group(1)
        if tool_name not in tools:
            continue

        args: dict[str, Any] = {}
        # Extract parameters: <parameter=NAME>value</parameter>
        for param_match in re.finditer(
            r"<parameter\s*=\s*([^\>>\s'\"]+)>(.*?)</parameter>",
            block,
            flags=re.DOTALL,
        ):
            param_name = param_match.group(1)
            raw_value = param_match.group(2).strip()
            try:
                args[param_name] = json.loads(raw_value)
            except json.JSONDecodeError:
                args[param_name] = raw_value

        # Extract parameters: <parameter name="NAME">value</parameter>
        for param_match in re.finditer(
            r'<parameter\s+name\s*=\s*["\']([^"\']+)["\']>(.*?)</parameter>',
            block,
            flags=re.DOTALL,
        ):
            param_name = param_match.group(1)
            raw_value = param_match.group(2).strip()
            try:
                args[param_name] = json.loads(raw_value)
            except json.JSONDecodeError:
                args[param_name] = raw_value

        parsed.append(
            _ParsedToolCall(
                id=f"legacy_call_{call_index}",
                name=tool_name,
                arguments=json.dumps(args),
            )
        )
        call_index += 1

    if parsed:
        logger.info("runner.legacy_tool_calls_extracted", count=len(parsed), tools=[tc.function.name for tc in parsed])

    return parsed


def extract_tool_calls(message, tools: Dict[str, Callable]) -> list[Any]:
    """Return tool_calls from the message object, falling back to XML/JSON/legacy parsing."""
    if getattr(message, "tool_calls", None):
        return message.tool_calls
    content = message.content or ""
    xml_calls = extract_xml_tool_calls(content)
    if xml_calls:
        return xml_calls
    json_calls = extract_json_tool_calls(content, tools)
    if json_calls:
        return json_calls
    return extract_legacy_tool_calls(content, tools)


def strip_xml_tool_calls(content: str) -> str:
    """Remove <function_calls> blocks from message content, preserving surrounding text."""
    return re.sub(r"<function_calls>.*?</function_calls>", "", content, flags=re.DOTALL).strip()


def strip_json_tool_calls(content: str, tools: Dict[str, Callable]) -> str:
    """Remove JSON tool call blobs from message content, preserving surrounding text."""
    if "{" not in content:
        return content

    # Same brace-matching logic as extract_json_tool_calls, but we remove matches
    result_parts: list[str] = []
    depth = 0
    start: int | None = None
    last_end = 0
    for i, ch in enumerate(content):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                obj_str = content[start : i + 1]
                try:
                    blob = json.loads(obj_str)
                    if (
                        isinstance(blob, dict)
                        and "name" in blob
                        and "arguments" in blob
                        and blob["name"] in tools
                    ):
                        # Append text before this JSON blob
                        result_parts.append(content[last_end:start])
                        last_end = i + 1
                except (json.JSONDecodeError, ValueError):
                    pass
                start = None

    result_parts.append(content[last_end:])
    return "".join(result_parts).strip()


def strip_legacy_tool_calls(content: str) -> str:
    """Remove <tool_call> blocks from message content, preserving surrounding text."""
    return re.sub(r"<tool_call>.*?</tool_call>", "", content, flags=re.DOTALL).strip()


def strip_tool_calls(content: str, tools: Dict[str, Callable]) -> str:
    """Remove XML, JSON, and legacy tool call markup from message content."""
    content = strip_xml_tool_calls(content)
    content = strip_json_tool_calls(content, tools)
    content = strip_legacy_tool_calls(content)
    return content
