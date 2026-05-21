import asyncio
import inspect
import json
import structlog
import websockets
from typing import Any, Callable, Dict, List, Optional
from litellm import acompletion

from .client import CoreClient
from .logging import configure_logging
from .models import AgentConfig, Task
from .tools import (
    SKILL_TOOL_REGISTRY,
    normalize_skill_name,
    DATETIME_DEF,
    get_current_datetime,
)

logger = structlog.get_logger()

# Runtime params injected by the runner, not provided by the LLM
RUNTIME_INJECTED_PARAMS = {"agent_id", "core_client"}


class AgentRunner:
    """
    The Opinionated ISLI Agent Runner.
    Automates heartbeats, WebSocket connectivity, context injection,
    and the ReAct execution loop with dual-checkpointing.
    """

    def __init__(self, config: AgentConfig, core_url: str, admin_key: Optional[str] = None):
        self.config = config
        self.core_url = core_url
        self.client = CoreClient(core_url, admin_key=admin_key)
        self.tools: Dict[str, Callable] = {}
        self.tool_definitions: List[Dict[str, Any]] = []
        self._running = False

    def add_tool(self, name: str, func: Callable, definition: Dict[str, Any]):
        """Register a tool with the agent."""
        self.tools[name] = func
        self.tool_definitions.append(definition)

    def add_workspace_tools(self):
        """Convenience method to register all workspace file tools."""
        from .tools import (
            file_read,
            FILE_READ_DEF,
            file_write,
            FILE_WRITE_DEF,
            file_list,
            FILE_LIST_DEF,
            file_delete,
            FILE_DELETE_DEF,
        )

        self.add_tool("file_read", file_read, FILE_READ_DEF)
        self.add_tool("file_write", file_write, FILE_WRITE_DEF)
        self.add_tool("file_list", file_list, FILE_LIST_DEF)
        self.add_tool("file_delete", file_delete, FILE_DELETE_DEF)

    def add_channel_tools(self):
        """Convenience method to register channel communication tools."""
        from .tools import send_message, SEND_MESSAGE_DEF

        self.add_tool("send_message", send_message, SEND_MESSAGE_DEF)

    def _auto_register_tools_from_skills(self):
        """Register tools based on the synced config.skills list from Core."""
        for skill_name in (self.config.skills or []):
            normalized = normalize_skill_name(skill_name)
            if normalized in SKILL_TOOL_REGISTRY:
                func, definition = SKILL_TOOL_REGISTRY[normalized]
                self.add_tool(normalized, func, definition)
                logger.info("runner.tool_registered", tool=normalized, skill=skill_name)
            else:
                logger.warning("runner.tool_not_found", skill=skill_name)

    async def _execute_tool(self, tool_name: str, tool_args: dict) -> str:
        """Execute a single tool call with runtime dependency injection."""
        tool_func = self.tools.get(tool_name)
        if not tool_func:
            return f"Error: Tool {tool_name} not found"

        sig = inspect.signature(tool_func)
        if "agent_id" in sig.parameters:
            tool_args["agent_id"] = self.config.id
        if "core_client" in sig.parameters:
            tool_args["core_client"] = self.client

        try:
            if asyncio.iscoroutinefunction(tool_func):
                result = await tool_func(**tool_args)
            else:
                result = tool_func(**tool_args)
            return str(result)
        except Exception as e:
            return f"Error executing tool: {str(e)}"

    def _assemble_system_prompt(self, context_summary: str) -> str:
        """Assemble the system prompt from identity, tools, and context."""
        lines = [
            "=== IDENTITY ===",
            f"Name: {self.config.name}",
            f"Description: {self.config.description or 'No description provided.'}",
        ]
        if self.config.persona:
            lines.append(f"Persona: {self.config.persona}")
        lines.append("")
        lines.append("=== AVAILABLE TOOLS ===")
        lines.append("You have access to the following tools. Call them when appropriate.")
        for definition in self.tool_definitions:
            func_name = definition.get("function", {}).get("name", "unknown")
            func_desc = definition.get("function", {}).get("description", "No description.")
            lines.append(f"- {func_name}: {func_desc}")
        lines.append("")
        lines.append("=== CONTEXT ===")
        lines.append(context_summary)
        lines.append("")
        lines.append("Use the tools when you need to interact with external systems.")
        return "\n".join(lines)

    async def start(self):
        """Start the agent: registration, heartbeat, and WebSocket listener."""
        self._running = True
        configure_logging(self.config.id)
        logger.info("runner.starting", agent_id=self.config.id)

        # 1. Register with Core and sync config
        reg_data = await self.client.register(self.config)
        if reg_data:
            self.config = AgentConfig.model_validate(reg_data)
            logger.info(
                "runner.config_synced",
                agent_id=self.config.id,
                skills=self.config.skills,
            )

        # 2. Auto-register tools from synced skills
        self._auto_register_tools_from_skills()

        # 3. Always register the datetime system tool
        self.add_tool("get_current_datetime", get_current_datetime, DATETIME_DEF)

        # 4. Start heartbeat loop in background
        asyncio.create_task(self._heartbeat_loop())

        # 5. Start WebSocket listener (main loop)
        await self._ws_loop()

    async def _heartbeat_loop(self):
        """Background loop to maintain agent's online status."""
        while self._running:
            try:
                await self.client.heartbeat(self.config.id)
                logger.debug("runner.heartbeat_success", agent_id=self.config.id)
            except Exception as e:
                logger.error("runner.heartbeat_failed", error=str(e))
            await asyncio.sleep(self.config.heartbeat_interval)

    async def _ws_loop(self):
        """WebSocket listener for incoming task assignments."""
        retry_delay = 1.0
        max_delay = 60.0

        while self._running:
            token = self.client.token
            if not token:
                await asyncio.sleep(1)
                continue

            ws_url = self.core_url.replace("http", "ws") + f"/v1/ws/agents/{self.config.id}?token={token}"
            try:
                async with websockets.connect(ws_url) as websocket:
                    logger.info(
                        "runner.ws_connected",
                        url=self.core_url + f"/v1/ws/agents/{self.config.id}",
                    )
                    retry_delay = 1.0  # Reset delay on success
                    async for message in websocket:
                        event = json.loads(message)
                        if event["type"] in ("task:created", "task:updated", "task:moved"):
                            task_data = event["payload"]["task"]
                            if task_data["status"] == "inbox":
                                logger.info("runner.task_detected", task_id=task_data["id"])
                                asyncio.create_task(self._execute_task(task_data["id"]))
                        elif event["type"] == "session:message":
                            payload = event["payload"]
                            logger.info(
                                "runner.session_message_detected",
                                session_id=payload.get("session_id"),
                            )
                            asyncio.create_task(self._execute_session_message(payload))
            except Exception as e:
                if self._running:
                    logger.error("runner.ws_error", error=str(e), next_retry=retry_delay)
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_delay)

    async def _execute_task(self, task_id: str):
        """Execute a single task using the ReAct pattern."""
        logger.info("runner.executing_task", task_id=task_id)
        try:
            # 1. Transition task to 'doing'
            await self.client.move_task(task_id, "doing")

            # 2. Fetch full task details
            task = await self.client.get_task(task_id)

            # 3. Get latest context injection (routes through Core to Keeper)
            context_summary = await self.client.get_context(
                self.config.id,
                task.description or task.title,
                session_id=task.session_id,
            )

            system_prompt = self._assemble_system_prompt(context_summary)
            messages = [{"role": "user", "content": task.input}]

            turn_number = 0
            while True:
                turn_number += 1
                logger.info("runner.turn_start", task_id=task_id, turn=turn_number)

                # 4. LLM Completion via LiteLLM
                response = await acompletion(
                    model=f"{self.config.model_provider}/{self.config.model_id}",
                    messages=[{"role": "system", "content": system_prompt}] + messages,
                    tools=self.tool_definitions if self.tool_definitions else None,
                )

                choice = response.choices[0]
                message = choice.message

                # Convert message to dict for storage
                msg_dict = message.model_dump()
                # LiteLLM sometimes has extra fields, ensure clean dict
                if "tool_calls" in msg_dict and msg_dict["tool_calls"] is None:
                    del msg_dict["tool_calls"]

                messages.append(msg_dict)

                if not message.tool_calls:
                    # Final response received
                    await self.client.complete_task(task_id, message.content or "")
                    logger.info("runner.task_success", task_id=task_id)
                    break

                # 5. Handle Tool Execution
                # CHECKPOINT 1: Pre-Execution (As required by Plan Phase 4)
                await self.client.save_checkpoint(
                    task_id,
                    turn_number,
                    messages,
                    tool_calls=[tc.model_dump() for tc in message.tool_calls],
                )

                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)

                    logger.info("runner.invoking_tool", tool=tool_name, args=tool_args)
                    result = await self._execute_tool(tool_name, tool_args)

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": result,
                    })

                # CHECKPOINT 2: Post-Execution (As required by Plan Phase 4)
                await self.client.save_checkpoint(task_id, turn_number, messages)

        except Exception as e:
            logger.error("runner.task_fatal_error", task_id=task_id, error=str(e))
            await self.client.complete_task(task_id, f"Fatal error: {str(e)}", status="failed")

    async def _execute_session_message(self, payload: dict):
        """Execute a session message using the ReAct pattern."""
        session_id = payload.get("session_id")
        logger.info("runner.executing_session_message", session_id=session_id)
        try:
            context_summary = payload.get("context_summary") or ""
            system_prompt = self._assemble_system_prompt(context_summary)

            # Start with existing session messages
            messages = list(payload.get("messages", []))

            turn_number = 0
            while True:
                turn_number += 1
                logger.info(
                    "runner.turn_start", session_id=session_id, turn=turn_number
                )

                response = await acompletion(
                    model=f"{self.config.model_provider}/{self.config.model_id}",
                    messages=[{"role": "system", "content": system_prompt}] + messages,
                    tools=self.tool_definitions if self.tool_definitions else None,
                )

                choice = response.choices[0]
                message = choice.message

                msg_dict = message.model_dump()
                if "tool_calls" in msg_dict and msg_dict["tool_calls"] is None:
                    del msg_dict["tool_calls"]

                messages.append(msg_dict)

                if not message.tool_calls:
                    # Final response received
                    final_text = message.content or ""
                    try:
                        await self.client.reply_to_session(session_id, final_text)
                        logger.info(
                            "runner.session_reply_sent", session_id=session_id
                        )
                    except Exception as e:
                        logger.error(
                            "runner.session_reply_failed",
                            session_id=session_id,
                            error=str(e),
                        )
                    break

                # Handle Tool Execution
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)

                    logger.info(
                        "runner.invoking_tool", tool=tool_name, args=tool_args
                    )
                    result = await self._execute_tool(tool_name, tool_args)

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": result,
                    })

        except Exception as e:
            logger.error(
                "runner.session_message_fatal_error",
                session_id=session_id,
                error=str(e),
            )
            try:
                await self.client.reply_to_session(
                    session_id, f"Fatal error: {str(e)}"
                )
            except Exception as reply_err:
                logger.error(
                    "runner.session_reply_failed",
                    session_id=session_id,
                    error=str(reply_err),
                )

    async def stop(self):
        """Gracefully stop the agent."""
        self._running = False
        await self.client.close()
