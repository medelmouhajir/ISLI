"""Discover-skills tool: lets an agent list all its assigned capabilities locally."""

from typing import Any


def discover_skills(all_definitions: list[dict[str, Any]]) -> str:
    """List all skills assigned to this agent from the runner's local registry.

    This tool reads from the in-memory registry — zero HTTP calls.
    """
    lines = []
    for defn in all_definitions:
        func = defn.get("function", {})
        name = func.get("name", "unknown")
        desc = func.get("description", "No description")
        lines.append(f"- {name}: {desc}")
    return "\n".join(lines)


DISCOVER_SKILLS_DEF = {
    "type": "function",
    "function": {
        "name": "discover_skills",
        "description": (
            "List all skills available to this agent. "
            "Use this when you need a capability that is not currently visible in your tool list."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "x_isli_always_active": True,
}
