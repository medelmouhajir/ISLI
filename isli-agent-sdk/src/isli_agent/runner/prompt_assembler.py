"""System-prompt assembly and tool-result fallback summaries."""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from .core import AgentRunner

logger = structlog.get_logger()


class PromptAssembler:
    """Assembles system prompts from identity, tools, and context."""

    def __init__(self, runner: "AgentRunner"):
        self.runner = runner

    def assemble(
        self,
        context_summary: str,
        session_info: dict | None = None,
        relevant_skills: list[str] | None = None,
        task_mode: bool = False,
    ) -> str:
        """Assemble the system prompt from identity, tools, and context."""
        from ..prompts_loader import get_prompts

        config = self.runner.config
        prompts = get_prompts()
        template = prompts["agent"]["system_prompt_template"]

        persona_line = f"Persona: {config.persona}\n" if config.persona else ""
        active_defs = self.runner._filter_tools_by_relevance(relevant_skills)
        if active_defs:
            tools_list = "\n".join(
                f"- {definition.get('function', {}).get('name', 'unknown')}: "
                f"{definition.get('function', {}).get('description', 'No description.')}"
                for definition in active_defs
            )
        else:
            tools_list = ""

        logger.debug("runner.assemble_prompt", tools=tools_list, task_mode=task_mode)

        system_prompt = template.format(
            name=config.name,
            description=config.description or "No description provided.",
            persona_line=persona_line,
            tools_list=tools_list,
            context_summary=context_summary,
            context_timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # Inject task-mode execution discipline when running a Kanban task.
        if task_mode:
            block = prompts.get("agent", {}).get("task_execution_block")
            if block:
                system_prompt += "\n\n" + block
            else:
                logger.warning("runner.task_execution_block_missing")

        # Inject council room discipline when the session belongs to a room.
        if session_info and session_info.get("room_id"):
            block = prompts.get("agent", {}).get("council_mode_block")
            if block:
                system_prompt += "\n\n" + block
            else:
                logger.warning("runner.council_mode_block_missing")

        # Inject current session metadata so the agent knows who it's talking to
        if session_info:
            user_id = session_info.get("user_id")
            channel = session_info.get("channel")
            sess_id = session_info.get("session_id")
            room_id = session_info.get("room_id")
            # Web sessions may not have a user_id; fall back to session_id
            effective_user_id = user_id or sess_id
            if effective_user_id or channel or sess_id or room_id:
                system_prompt += "\n\n=== CURRENT SESSION ===\n"
                if effective_user_id:
                    system_prompt += f"User ID: {effective_user_id}\n"
                if channel:
                    system_prompt += f"Channel: {channel}\n"
                if sess_id:
                    system_prompt += f"Session ID: {sess_id}\n"
                if room_id:
                    system_prompt += f"Room ID: {room_id}\n"
                system_prompt += (
                    "Use the User ID above when calling tools that require a user_id parameter. "
                    "If the user asks you to send a notification or message, use this identifier."
                )

        # Inject peer agents so the LLM knows who it can delegate to
        if config.known_agent_ids:
            system_prompt += "\n\n=== PEER AGENTS ===\n"
            system_prompt += (
                "You can delegate tasks to the following agents via the Kanban board. "
                "Use the create_task tool and assign it to one of these agent IDs:\n"
            )
            for peer_id in config.known_agent_ids:
                system_prompt += f"- {peer_id}\n"
            system_prompt += (
                "\nWhen delegating, include a clear task description and set the "
                "assignee to the target agent's ID."
            )

        # Conditionally inject UI rendering instructions
        if config.skills and "ui-components" in config.skills:
            from ..tools.ui_renderer import UI_RENDERING_INSTRUCTIONS
            system_prompt += "\n\n" + UI_RENDERING_INSTRUCTIONS

        return system_prompt

    @staticmethod
    def build_tool_fallback_summary(messages: list[dict]) -> str:
        """Synthesize a short fallback answer from recent tool results.

        Used when the model returns an empty final response after using tools.
        Prevents the agent from sending a blank reply to the user.
        """
        tool_results: list[str] = []
        for m in messages:
            if m.get("role") == "tool" and m.get("content"):
                content = str(m["content"])
                # Skip error-only results; they are handled elsewhere.
                if content.startswith("Error:") or content.startswith("Validation Error:"):
                    continue
                # Keep it brief.
                summary = content[:300]
                if len(content) > 300:
                    summary += "..."
                tool_results.append(summary)
        if not tool_results:
            return "I processed your request but didn't generate a final response."
        if len(tool_results) == 1:
            return f"I checked the relevant source and found: {tool_results[0]}"
        joined = "\n- ".join(tool_results)
        return f"I gathered the following information:\n- {joined}"
