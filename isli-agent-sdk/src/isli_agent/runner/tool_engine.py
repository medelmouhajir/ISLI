"""Tool registry, dynamic skill discovery, execution, and relevance filtering."""

import asyncio
import inspect
import json
import time
from typing import TYPE_CHECKING, Any, Callable, Dict

from pydantic import ValidationError

import structlog

from ..tools import (
    SKILL_NAME_ALIASES,
    SKILL_TOOL_REGISTRY,
    fetch_dynamic_tools,
    normalize_skill_name,
)
from .constants import TOOL_RESULT_SPILL_THRESHOLD
from .sanitize import _sanitize_tool_result

if TYPE_CHECKING:
    from .core import AgentRunner

logger = structlog.get_logger()


class ToolEngine:
    """Manages tool registration, dynamic discovery, execution, and per-turn filtering."""

    def __init__(self, runner: "AgentRunner"):
        self.runner = runner

    def add_tool(self, name: str, func: Callable, definition: Dict[str, Any], skill_name: str | None = None):
        """Register a tool with the agent."""
        # Wrap with Pydantic validation for strict type checking
        from pydantic import validate_call
        self.runner.tools[name] = validate_call(func, config={"strict": True, "arbitrary_types_allowed": True})  # type: ignore[call-overload]
        if skill_name:
            definition["x_isli_skill"] = skill_name
        self.runner.tool_definitions.append(definition)

    def add_dynamic_tool(self, name: str, func: Callable, definition: Dict[str, Any], skill_name: str | None = None):
        """Register a dynamic skill tool without Pydantic validation (generic **kwargs proxy)."""
        if skill_name:
            definition["x_isli_skill"] = skill_name
        self.runner.tools[name] = func
        self.runner.tool_definitions.append(definition)

    async def auto_register_from_skills(self):
        """Register tools based on the synced config.skills list from Core.

        Also fetches dynamic tools from Core's skill registry for any skills
        not present in the static SDK registry.
        """
        config = self.runner.config
        client = self.runner.client
        skills_to_register = config.skills or []
        logger.info("runner.auto_register_tools", skills=skills_to_register)

        # Fetch dynamic tools from Core once
        dynamic_tools, skill_tools_map = await fetch_dynamic_tools(client)

        for skill_name in skills_to_register:
            normalized = normalize_skill_name(skill_name)
            registry_key = SKILL_NAME_ALIASES.get(normalized, normalized)
            if registry_key in SKILL_TOOL_REGISTRY:
                func, definition = SKILL_TOOL_REGISTRY[registry_key]
                self.add_tool(registry_key, func, definition, skill_name=skill_name)
                logger.info("runner.tool_registered", tool=registry_key, skill=skill_name)
            elif normalized in skill_tools_map:
                # Register all tools belonging to this dynamic skill
                for tool_name in skill_tools_map[normalized]:
                    func, definition = dynamic_tools[tool_name]
                    self.add_dynamic_tool(tool_name, func, definition, skill_name=registry_key)
                    logger.info("runner.dynamic_tool_registered", tool=tool_name, skill=skill_name)
            else:
                logger.warning("runner.tool_not_found", skill=skill_name, normalized=normalized, available=list(SKILL_TOOL_REGISTRY.keys()))

    async def execute(self, tool_name: str, tool_args: dict, session_id: str | None = None) -> str:
        """Execute a single tool call with runtime dependency injection."""
        tool_func = self.runner.tools.get(tool_name)
        if not tool_func:
            return f"Error: Tool {tool_name} not found"

        sig = inspect.signature(tool_func)
        if "agent_id" in sig.parameters:
            tool_args["agent_id"] = self.runner.config.id
        if "core_client" in sig.parameters:
            tool_args["core_client"] = self.runner.client
        if "runner" in sig.parameters:
            tool_args["runner"] = self.runner
        if "session_id" in sig.parameters:
            tool_args["session_id"] = session_id

        start_time = time.monotonic()
        try:
            if asyncio.iscoroutinefunction(tool_func):
                result = await tool_func(**tool_args)
            else:
                result = tool_func(**tool_args)

            # Intercept ui_components to stash for the final reply
            if (
                tool_name == "ui_components"
                and isinstance(result, dict)
                and "component_type" in result
            ):
                self.runner._pending_components.append(result)
                result = (
                    f"Component '{result['component_type']}' rendered with action_id "
                    f"'{result.get('action_id')}'. It will appear inline in the chat."
                )

            # Capture audio payload before sanitization so it can be attached
            # to the final session reply automatically.
            if (
                session_id
                and tool_name == "text_to_speech"
                and isinstance(result, dict)
                and isinstance(result.get("audio_b64"), str)
            ):
                self.runner._pending_audio[session_id] = {
                    "audio_b64": result["audio_b64"],
                    "voice": result.get("voice"),
                }

            latency_ms = round((time.monotonic() - start_time) * 1000, 2)
            result_str = str(_sanitize_tool_result(result))

            # PHASE 1: Hybrid Threshold Spill
            if len(result_str) > TOOL_RESULT_SPILL_THRESHOLD:
                filename = f"spill_{tool_name}_{int(time.time())}.txt"
                logger.info("runner.tool_output_spilling", tool=tool_name, size=len(result_str), filename=filename)
                try:
                    # Write to workspace via core_client proxy
                    await self.runner.client.client.post(
                        "/v1/skills/file-write/write",
                        json={
                            "agent_id": self.runner.config.id,
                            "path": filename,
                            "content": result_str,
                            "scope": "agent",
                            "scope_id": self.runner.config.id
                        },
                        headers=self.runner.client._get_headers(),
                    )
                    # Replace result_str with structured envelope
                    spill_envelope = {
                        "status": "spilled",
                        "token_estimate": len(result_str) // 4,
                        "workspace_path": filename,
                        "hint": "Use describe_workspace_file to understand structure, then search_workspace_file or read_workspace_file to access contents.",
                        "preview": result_str[:300] + "..."
                    }
                    result_str = json.dumps(spill_envelope)
                except Exception as spill_err:
                    logger.error("runner.spill_failed", error=str(spill_err))
                    # Fallback: standard truncation
                    result_str = result_str[:TOOL_RESULT_SPILL_THRESHOLD] + f"\n... [{len(result_str)} chars truncated - Spill Failed]"

            logger.info(
                "runner.tool_execution",
                tool=tool_name,
                args=tool_args,
                latency_ms=latency_ms,
                raw_output=result_str[:2000]
            )
            return result_str
        except ValidationError as e:
            # Surface exact schema mismatch as a prominent warning
            error_data = e.errors()
            logger.warning(
                "runner.tool_validation_failed",
                tool=tool_name,
                error=str(e),
                errors=error_data
            )
            # Return structured feedback to the LLM to improve self-correction
            return f"Error: Tool arguments failed schema validation:\n{json.dumps(error_data, indent=2, default=str)}"
        except Exception as e:
            logger.error("runner.tool_execution_failed", tool=tool_name, error=str(e))
            return f"Error executing tool: {str(e)}"

    def filter_by_relevance(self, relevant_skills: list[str] | None) -> list[dict[str, Any]]:
        """Return a subset of tool definitions based on Keeper's intent classification.

        Behavior is controlled by ``config.tool_injection_strategy``:

        - ``auto`` (default): filter by ``relevant_skills``; fall back to the full
          set when Keeper returns empty / none.
        - ``all``: skip filtering entirely; always return the full tool set.
        - ``strict``: filter even when ``relevant_skills`` is empty, so only
          ``x_isli_always_active`` tools survive a blank classification.
        """
        config = self.runner.config
        strategy = config.config.get("tool_injection_strategy", "auto")
        all_defs = getattr(self.runner, "_all_tool_definitions", None) or self.runner.tool_definitions

        if strategy == "all":
            logger.info(
                "runner.tools_filtered",
                strategy=strategy,
                active_count=len(all_defs),
                total_count=len(all_defs),
            )
            return all_defs

        if strategy == "auto" and not relevant_skills:
            logger.info(
                "runner.tools_filtered",
                strategy=strategy,
                active_count=len(all_defs),
                total_count=len(all_defs),
            )
            return all_defs

        active_set: set[str] = set()
        for skill_name in relevant_skills or []:
            normalized = normalize_skill_name(skill_name)
            registry_key = SKILL_NAME_ALIASES.get(normalized, normalized)
            active_set.add(registry_key)

        filtered = [
            defn for defn in all_defs
            if defn.get("function", {}).get("name") in active_set
            or defn.get("x_isli_skill") in active_set
            or defn.get("x_isli_always_active", False)
        ]
        logger.info(
            "runner.tools_filtered",
            strategy=strategy,
            requested=relevant_skills,
            active_count=len(filtered),
            total_count=len(all_defs),
        )
        return filtered
