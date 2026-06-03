from typing import Any, Optional, List
from isli_agent.client import CoreClient


def _get_tool_desc(name: str, default: str) -> str:
    try:
        from isli_agent.prompts_loader import get_prompts
        return get_prompts()["agent"]["tool_descriptions"].get(name, default)
    except Exception:
        return default


async def interactive_debugger(
    code: str,
    core_client: CoreClient = None,
    payload: Optional[dict[str, Any]] = None,
    breakpoints: Optional[List[int]] = None,
    mode: str = "breakpoints",
    max_steps: int = 1000,
    max_trace_size: int = 32768,
    only_changes: bool = True,
    include_locals: bool = True,
    include_globals: bool = False,
    watch_expressions: Optional[List[str]] = None,
    stdin: str = "",
) -> dict[str, Any]:
    """Run code in an interactive debugger with breakpoints, variable inspection,
    and line-by-line execution trace.
    """
    if core_client is None:
        raise ValueError("core_client is required")

    return await core_client.invoke_skill(
        skill_name="interactive-debugger",
        action="debug",
        payload={
            "code": code,
            "payload": payload or {},
            "breakpoints": breakpoints or [],
            "mode": mode,
            "max_steps": max_steps,
            "max_trace_size": max_trace_size,
            "only_changes": only_changes,
            "include_locals": include_locals,
            "include_globals": include_globals,
            "watch_expressions": watch_expressions or [],
            "stdin": stdin,
        },
    )


INTERACTIVE_DEBUGGER_DEF = {
    "type": "function",
    "function": {
        "name": "interactive_debugger",
        "description": _get_tool_desc(
            "interactive_debugger",
            "Run code in an interactive debugger with breakpoints, variable inspection, and line-by-line execution trace. Use this to diagnose bugs by watching variables change across execution.",
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to debug",
                },
                "payload": {
                    "type": "object",
                    "description": "JSON payload to inject into the code's namespace as 'payload'",
                },
                "breakpoints": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Line numbers to pause at and capture detailed state",
                },
                "mode": {
                    "type": "string",
                    "enum": ["trace", "breakpoints", "run"],
                    "description": "trace = every line; breakpoints = only at breakpoints; run = just final result",
                },
                "max_steps": {
                    "type": "integer",
                    "description": "Safety limit for trace steps (default 1000)",
                },
                "max_trace_size": {
                    "type": "integer",
                    "description": "Max bytes for the trace JSON response (default 32768)",
                },
                "only_changes": {
                    "type": "boolean",
                    "description": "Only include locals whose value changed vs the previous step (default true)",
                },
                "include_locals": {
                    "type": "boolean",
                    "description": "Include local variables in trace events (default true)",
                },
                "include_globals": {
                    "type": "boolean",
                    "description": "Include global variables in trace events (default false)",
                },
                "watch_expressions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Expressions to evaluate at each recorded step",
                },
                "stdin": {
                    "type": "string",
                    "description": "Input to feed to the program via sys.stdin",
                },
            },
            "required": ["code"],
        },
    },
}
