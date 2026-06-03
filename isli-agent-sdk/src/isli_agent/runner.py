import asyncio
import enum
import httpx
import inspect
import json
import random
import re
import time
import structlog
import websockets
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from litellm import (
    acompletion,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout as LiteLLMTimeoutError,
)

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


def _normalize_provider(provider: str) -> str:
    """
    Normalizes the model provider string to the format expected by LiteLLM.
    e.g., 'google' -> 'gemini', 'vertex' -> 'vertex_ai'
    """
    mapping = {
        "google": "gemini",
        "vertex": "vertex_ai",
    }
    normalized = mapping.get(provider.lower(), provider)
    if normalized != provider:
        logger.debug("runner.provider_normalized", original=provider, normalized=normalized)
    return normalized


CIRCUIT_HALF_OPEN_AFTER = 300  # 5 minutes


class ModelErrorCategory(enum.Enum):
    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    OVERLOADED = "overloaded"
    BAD_REQUEST = "bad_request"
    UNKNOWN = "unknown"


def _classify_model_error(exc: Exception) -> tuple[ModelErrorCategory, str]:
    """Classify a LiteLLM exception. Primary: isinstance. Fallback: string inspection."""
    error_str = str(exc).lower()

    if isinstance(exc, AuthenticationError):
        return (ModelErrorCategory.AUTH, "The AI model's API key is invalid or has expired. Please contact the administrator.")

    if isinstance(exc, RateLimitError):
        return (ModelErrorCategory.RATE_LIMIT, "The AI model is currently rate-limited. Please try again in a moment.")

    if isinstance(exc, LiteLLMTimeoutError):
        return (ModelErrorCategory.TIMEOUT, "Connection to the AI model timed out. Please try again shortly.")

    if isinstance(exc, ServiceUnavailableError):
        return (ModelErrorCategory.OVERLOADED, "The AI model is temporarily overloaded. Please try again in a moment.")

    if isinstance(exc, BadRequestError):
        if "api key" in error_str:
            return (ModelErrorCategory.AUTH, "The AI model's API key is invalid or has expired. Please contact the administrator.")
        return (ModelErrorCategory.BAD_REQUEST, "The request could not be processed by the AI model. It may be too long or contain unsupported content.")

    # String fallback for provider-specific errors LiteLLM doesn't wrap
    if any(k in error_str for k in ("api key not valid", "unauthorized", "auth", "invalid token", "permission denied")):
        return (ModelErrorCategory.AUTH, "The AI model's API key is invalid or has expired. Please contact the administrator.")
    if "rate limit" in error_str or "too many requests" in error_str:
        return (ModelErrorCategory.RATE_LIMIT, "The AI model is currently rate-limited. Please try again in a moment.")
    if "api connection error" in error_str or "timeout" in error_str:
        return (ModelErrorCategory.TIMEOUT, "Connection to the AI model timed out. Please try again shortly.")
    if "overloaded" in error_str or "temporarily unavailable" in error_str:
        return (ModelErrorCategory.OVERLOADED, "The AI model is temporarily overloaded. Please try again in a moment.")

    return (ModelErrorCategory.UNKNOWN, "An unexpected error occurred while talking to the AI model. The administrator has been notified.")


def _sanitize_tool_result(result: Any) -> Any:
    """Strip large binary payloads from tool results before they reach the LLM.

    Base64 audio/images can be megabytes; feeding them back into the model
    context causes token explosions and timeouts.  We preserve metadata so
    the LLM still knows the tool succeeded.
    """
    if not isinstance(result, dict):
        return result

    sanitized = dict(result)
    if "audio_b64" in sanitized and isinstance(sanitized["audio_b64"], str):
        audio_len = len(sanitized["audio_b64"])
        sanitized["audio_b64"] = (
            f"<{audio_len} chars of base64 audio omitted — "
            f"use send_message(audio_b64=...) to deliver to user>"
        )
    # Also truncate any other unexpectedly long string fields
    for key, value in sanitized.items():
        if isinstance(value, str) and len(value) > 10_000:
            sanitized[key] = value[:5000] + f"\n... [{len(value)} chars truncated]"
    return sanitized


class AgentRunner:
    """
    The Opinionated ISLI Agent Runner.
    Automates heartbeats, WebSocket connectivity, context injection,
    and the ReAct execution loop with dual-checkpointing.
    """

    def __init__(self, config: AgentConfig, core_url: str, admin_key: Optional[str] = None):
        # Guard: default model must be configured. These are the ground-truth
        # fallback for model routing. Fail loudly at startup if missing.
        if not config.model_provider or not config.model_id:
            raise ValueError(
                f"Agent {config.id} must have model_provider and model_id configured. "
                "These are the ground-truth fallback for model routing."
            )
        self.config = config
        self.core_url = core_url
        self.client = CoreClient(core_url, admin_key=admin_key)
        self.tools: Dict[str, Callable] = {}
        self.tool_definitions: List[Dict[str, Any]] = []
        self._running = False
        self._pending_components: List[Dict[str, Any]] = []
        self._inflight_sessions: set = set()
        self._websocket: Optional[Any] = None
        self._outgoing_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._current_session_metadata: dict = {}
        # Pending audio generated by text_to_speech to attach to the next session reply
        self._pending_audio: dict[str, dict[str, Any]] = {}
        # Circuit breaker for sustained model auth failures
        self._model_circuit_open: bool = False
        self._circuit_open_reason: str | None = None
        self._circuit_tripped_at: float | None = None
        self._consecutive_auth_failures: int = 0

    def add_tool(self, name: str, func: Callable, definition: Dict[str, Any]):
        """Register a tool with the agent."""
        from pydantic import validate_call
        # Wrap with Pydantic validation for strict type checking
        self.tools[name] = validate_call(func, config={"strict": True, "arbitrary_types_allowed": True})
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

    def add_notification_tools(self):
        """Convenience method to register the notify_user tool."""
        from .tools import notify_user, NOTIFY_USER_DEF

        self.add_tool("notify_user", notify_user, NOTIFY_USER_DEF)

    def _auto_register_tools_from_skills(self):
        """Register tools based on the synced config.skills list from Core."""
        from isli_agent.tools import SKILL_NAME_ALIASES
        skills_to_register = self.config.skills or []
        logger.info("runner.auto_register_tools", skills=skills_to_register)
        for skill_name in skills_to_register:
            normalized = normalize_skill_name(skill_name)
            registry_key = SKILL_NAME_ALIASES.get(normalized, normalized)
            if registry_key in SKILL_TOOL_REGISTRY:
                func, definition = SKILL_TOOL_REGISTRY[registry_key]
                self.add_tool(registry_key, func, definition)
                logger.info("runner.tool_registered", tool=registry_key, skill=skill_name)
            else:
                logger.warning("runner.tool_not_found", skill=skill_name, normalized=normalized, available=list(SKILL_TOOL_REGISTRY.keys()))

    async def _execute_tool(self, tool_name: str, tool_args: dict, session_id: str | None = None) -> str:
        """Execute a single tool call with runtime dependency injection."""
        from pydantic import ValidationError

        tool_func = self.tools.get(tool_name)
        if not tool_func:
            return f"Error: Tool {tool_name} not found"

        sig = inspect.signature(tool_func)
        if "agent_id" in sig.parameters:
            tool_args["agent_id"] = self.config.id
        if "core_client" in sig.parameters:
            tool_args["core_client"] = self.client

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
                self._pending_components.append(result)
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
                self._pending_audio[session_id] = {
                    "audio_b64": result["audio_b64"],
                    "voice": result.get("voice"),
                }

            latency_ms = round((time.monotonic() - start_time) * 1000, 2)
            result_str = str(_sanitize_tool_result(result))

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

    def _extract_xml_tool_calls(self, content: str) -> list[_ParsedToolCall]:
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

    def _extract_json_tool_calls(self, content: str) -> list[_ParsedToolCall]:
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
                and blob["name"] in self.tools
            ):
                parsed.append(
                    _ParsedToolCall(
                        id=f"json_call_{len(parsed)}",
                        name=blob["name"],
                        arguments=json.dumps(blob["arguments"]),
                    )
                )

        return parsed

    def _extract_tool_calls(self, message) -> list[Any]:
        """Return tool_calls from the message object, falling back to XML/JSON parsing."""
        if getattr(message, "tool_calls", None):
            return message.tool_calls
        content = message.content or ""
        xml_calls = self._extract_xml_tool_calls(content)
        if xml_calls:
            return xml_calls
        return self._extract_json_tool_calls(content)

    @staticmethod
    def _strip_xml_tool_calls(content: str) -> str:
        """Remove <function_calls> blocks from message content, preserving surrounding text."""
        return re.sub(r"<function_calls>.*?</function_calls>", "", content, flags=re.DOTALL).strip()

    def _strip_json_tool_calls(self, content: str) -> str:
        """Remove JSON tool call blobs from message content, preserving surrounding text."""
        if "{" not in content:
            return content

        # Same brace-matching logic as _extract_json_tool_calls, but we remove matches
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
                            and blob["name"] in self.tools
                        ):
                            # Append text before this JSON blob
                            result_parts.append(content[last_end:start])
                            last_end = i + 1
                    except (json.JSONDecodeError, ValueError):
                        pass
                    start = None

        result_parts.append(content[last_end:])
        return "".join(result_parts).strip()

    def _strip_tool_calls(self, content: str) -> str:
        """Remove both XML and JSON tool call markup from message content."""
        content = self._strip_xml_tool_calls(content)
        content = self._strip_json_tool_calls(content)
        return content

    # ── Streaming infrastructure ────────────────────────────────────────────────

    def _resolve_streaming_mode(self, session_id: str) -> str:
        """Resolve streaming mode: session metadata > agent config > silent."""
        if self._current_session_metadata and "streaming_mode" in self._current_session_metadata:
            return self._current_session_metadata["streaming_mode"]
        if self.config.config:
            return self.config.config.get("streaming_mode", "silent")
        return "silent"

    async def _emit_stream_event(self, session_id: str, event_type: str, data: dict):
        """Emit a streaming event. NEVER raise — streaming is best-effort."""
        try:
            mode = self._resolve_streaming_mode(session_id)
            if mode == "silent":
                return
            if mode == "text" and event_type not in (
                "token_delta",
                "draft_complete",
                "tool_call",
                "error",
            ):
                return
            if mode == "tools" and event_type not in (
                "token_delta",
                "draft_complete",
                "tool_call",
                "error",
            ):
                return
            if mode == "trace" and event_type in ("debug_prompt", "debug_response"):
                return
            # debug mode allows everything

            event = {
                "type": "agent:stream_event",
                "payload": {
                    "session_id": session_id,
                    "event_type": event_type,
                    "data": data,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            }
            try:
                self._outgoing_queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    "runner.stream_queue_full",
                    session_id=session_id,
                    event_type=event_type,
                )
        except Exception as e:
            logger.warning(
                "runner.emit_stream_event_failed",
                session_id=session_id,
                event_type=event_type,
                error=str(e),
            )

    async def _stream_text(self, session_id: str, text: str):
        """Emit token_delta events by splitting text into configurable chunks."""
        cfg = self.config.config or {}
        chunk_size = cfg.get("stream_chunk_size", 5)
        delay_ms = cfg.get("stream_delay_ms", 20)
        if chunk_size < 1:
            chunk_size = 5
        if delay_ms < 0:
            delay_ms = 20

        for i in range(0, len(text), chunk_size):
            chunk = text[i : i + chunk_size]
            await self._emit_stream_event(session_id, "token_delta", {"delta": chunk})
            await asyncio.sleep(delay_ms / 1000)
        await self._emit_stream_event(session_id, "draft_complete", {})

    async def _drain_outgoing_queue(self):
        """Drain the outgoing queue to the active WebSocket."""
        while self._running:
            try:
                event = await asyncio.wait_for(self._outgoing_queue.get(), timeout=1.0)
                if self._websocket and getattr(self._websocket, "open", False):
                    await self._websocket.send(json.dumps(event))
                    await asyncio.sleep(0.001)
            except asyncio.TimeoutError:
                continue

    # ── Model / prompt resolution ─────────────────────────────────────────────

    def _resolve_model(self, routed: dict | None = None) -> str:
        """Pick the model string for LiteLLM.

        Priority:
        1. Routed model (if present and valid)
        2. Agent default model
        """
        if routed and routed.get("model_id"):
            provider = _normalize_provider(routed.get("provider", self.config.model_provider or ""))
            model_id = routed["model_id"]
            return f"{provider}/{model_id}"
        return f"{_normalize_provider(self.config.model_provider or '')}/{self.config.model_id}"

    async def _acompletion_with_retry(self, completion_kwargs: dict[str, Any], turn_label: str) -> Any:
        """Call acompletion with transient-error retry and ±50% jitter."""
        max_retries = 3
        base_delay = 1.0

        for attempt in range(max_retries):
            try:
                return await acompletion(**completion_kwargs)
            except Exception as exc:
                category, _ = _classify_model_error(exc)
                if category not in (ModelErrorCategory.RATE_LIMIT, ModelErrorCategory.TIMEOUT, ModelErrorCategory.OVERLOADED):
                    raise

                if attempt == max_retries - 1:
                    raise

                delay = min(base_delay * (2 ** attempt), 30.0)
                delay = delay * (0.5 + random.random() * 0.5)

                logger.warning(
                    "runner.model_retry",
                    turn=turn_label,
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    delay=round(delay, 2),
                    category=category.value,
                    error=str(exc),
                )
                await asyncio.sleep(delay)

    async def _model_with_fallback(self, completion_kwargs: dict, turn_label: str) -> Any:
        """Execute acompletion with deterministic fallback. Auth errors do NOT fallback."""
        routed = completion_kwargs.get("_routed_model")
        default = {"provider": self.config.model_provider, "model_id": self.config.model_id}

        if not default.get("model_id"):
            raise RuntimeError(
                "Agent default model is missing. "
                "Set model_provider + model_id on the agent record."
            )

        attempts: list[tuple[str, dict]] = []
        if routed and routed.get("model_id"):
            attempts.append(("routed", routed))
        attempts.append(("default", default))

        last_error: Exception | None = None
        for attempt_name, model_cfg in attempts:
            try:
                completion_kwargs["model"] = self._resolve_model(model_cfg)
                return await self._acompletion_with_retry(completion_kwargs, turn_label)
            except Exception as exc:
                last_error = exc
                category, _ = _classify_model_error(exc)
                if category == ModelErrorCategory.AUTH:
                    raise
                logger.warning(
                    "runner.model_fallback",
                    attempt=attempt_name,
                    from_model=completion_kwargs.get("model"),
                    category=category.value,
                    error=str(exc),
                )
        raise last_error or RuntimeError("No model available")

    def _assemble_system_prompt(self, context_summary: str, session_info: dict | None = None) -> str:
        """Assemble the system prompt from identity, tools, and context."""
        from .prompts_loader import get_prompts

        prompts = get_prompts()
        template = prompts["agent"]["system_prompt_template"]

        persona_line = f"Persona: {self.config.persona}\n" if self.config.persona else ""
        tools_list = "\n".join(
            f"- {definition.get('function', {}).get('name', 'unknown')}: "
            f"{definition.get('function', {}).get('description', 'No description.')}"
            for definition in self.tool_definitions
        )

        logger.debug("runner.assemble_prompt", tools=tools_list)

        system_prompt = template.format(
            name=self.config.name,
            description=self.config.description or "No description provided.",
            persona_line=persona_line,
            tools_list=tools_list,
            context_summary=context_summary,
            context_timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # Inject current session metadata so the agent knows who it's talking to
        if session_info:
            user_id = session_info.get("user_id")
            channel = session_info.get("channel")
            sess_id = session_info.get("session_id")
            # Web sessions may not have a user_id; fall back to session_id
            effective_user_id = user_id or sess_id
            if effective_user_id or channel or sess_id:
                system_prompt += "\n\n=== CURRENT SESSION ===\n"
                if effective_user_id:
                    system_prompt += f"User ID: {effective_user_id}\n"
                if channel:
                    system_prompt += f"Channel: {channel}\n"
                if sess_id:
                    system_prompt += f"Session ID: {sess_id}\n"
                system_prompt += (
                    "Use the User ID above when calling tools that require a user_id parameter. "
                    "If the user asks you to send a notification or message, use this identifier."
                )

        # Inject peer agents so the LLM knows who it can delegate to
        if self.config.known_agent_ids:
            system_prompt += "\n\n=== PEER AGENTS ===\n"
            system_prompt += (
                "You can delegate tasks to the following agents via the Kanban board. "
                "Use the create_task tool and assign it to one of these agent IDs:\n"
            )
            for peer_id in self.config.known_agent_ids:
                system_prompt += f"- {peer_id}\n"
            system_prompt += (
                "\nWhen delegating, include a clear task description and set the "
                "assignee to the target agent's ID."
            )

        # Conditionally inject UI rendering instructions
        if self.config.skills and "ui-components" in self.config.skills:
            from .tools.ui_renderer import UI_RENDERING_INSTRUCTIONS
            system_prompt += "\n\n" + UI_RENDERING_INSTRUCTIONS

        return system_prompt

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

        # 2. Restore circuit breaker from Core status (restart consistency)
        # Config may not always include status/status_reason, so use getattr guards
        agent_status = getattr(self.config, "status", None)
        agent_status_reason = getattr(self.config, "status_reason", None)
        if agent_status == "flagged" and agent_status_reason and "auth_error" in agent_status_reason:
            self._model_circuit_open = True
            self._circuit_open_reason = agent_status_reason
            # Allow immediate half-open probe on restart — operator may have fixed the key
            self._circuit_tripped_at = time.monotonic() - CIRCUIT_HALF_OPEN_AFTER - 1
            logger.warning(
                "runner.model_circuit_restored_from_core",
                agent_id=self.config.id,
                reason=self._circuit_open_reason,
            )

        # 3. Auto-register tools from synced skills
        self._auto_register_tools_from_skills()

        # 4. Always register the datetime system tool
        self.add_tool("get_current_datetime", get_current_datetime, DATETIME_DEF)

        # 5. Start heartbeat loop in background
        asyncio.create_task(self._heartbeat_loop())

        # 5. Start WebSocket listener (main loop)
        await self._ws_loop()

    async def _sync_config(self):
        """Dynamically re-sync configuration and reload tools from Core."""
        logger.info("runner.syncing_config", agent_id=self.config.id)
        try:
            # Re-register to get fresh config (idempotent)
            reg_data = await self.client.register(self.config)
            if reg_data:
                logger.debug("runner.sync_config.raw_data", skills=reg_data.get("skills"))
                self.config = AgentConfig.model_validate(reg_data)
                
                # Clear existing tools
                self.tools = {}
                self.tool_definitions = []
                
                # Re-register tools
                self._auto_register_tools_from_skills()
                self.add_tool("get_current_datetime", get_current_datetime, DATETIME_DEF)
                
                logger.info(
                    "runner.config_reloaded",
                    agent_id=self.config.id,
                    skills=self.config.skills,
                    tool_count=len(self.tools)
                )
        except Exception as e:
            logger.error("runner.sync_config_failed", error=str(e))

    async def _heartbeat_loop(self):
        """Background loop to maintain agent's online status."""
        while self._running:
            try:
                await self.client.heartbeat(self.config.id)
                logger.debug("runner.heartbeat_success", agent_id=self.config.id)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    logger.warning("runner.heartbeat_token_revoked", agent_id=self.config.id)
                    try:
                        await self.client.recover_token(self.config.id)
                        logger.info("runner.token_recovered", agent_id=self.config.id)
                        # Retry heartbeat immediately with the fresh token
                        await self.client.heartbeat(self.config.id)
                        logger.debug("runner.heartbeat_success_after_recovery", agent_id=self.config.id)
                    except Exception as rec_err:
                        logger.error("runner.token_recovery_failed", agent_id=self.config.id, error=str(rec_err))
                else:
                    logger.error("runner.heartbeat_failed", agent_id=self.config.id, error=str(e))
            except Exception as e:
                logger.error("runner.heartbeat_failed", agent_id=self.config.id, error=str(e))
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
                    self._websocket = websocket
                    logger.info(
                        "runner.ws_connected",
                        url=self.core_url + f"/v1/ws/agents/{self.config.id}",
                    )
                    retry_delay = 1.0  # Reset delay on success
                    drain_task = asyncio.create_task(self._drain_outgoing_queue())
                    try:
                        async for message in websocket:
                            event = json.loads(message)
                            if event["type"] in ("task:created", "task:updated", "task:moved"):
                                task_data = event["payload"]["task"]
                                if task_data["status"] == "inbox":
                                    logger.info("runner.task_detected", task_id=task_data["id"])
                                    asyncio.create_task(self._execute_task(task_data["id"]))
                            elif event["type"] == "agent:config_updated":
                                logger.info("runner.config_update_event_detected", agent_id=self.config.id)
                                asyncio.create_task(self._sync_config())
                            elif event["type"] == "session:message":
                                payload = event["payload"]
                                logger.info(
                                    "runner.session_message_detected",
                                    session_id=payload.get("session_id"),
                                )
                                # Store per-session metadata for streaming mode override
                                self._current_session_metadata = payload.get("metadata") or {}
                                asyncio.create_task(self._execute_session_message(payload))
                    finally:
                        drain_task.cancel()
                        self._websocket = None
            except Exception as e:
                if self._running:
                    error_str = str(e).lower()
                    if "401" in error_str or "403" in error_str or "policy violation" in error_str:
                        try:
                            await self.client.recover_token(self.config.id)
                            logger.info("runner.ws_token_recovered", agent_id=self.config.id)
                        except Exception as rec_err:
                            logger.error(
                                "runner.ws_token_recovery_failed",
                                agent_id=self.config.id,
                                error=str(rec_err),
                            )
                    logger.error("runner.ws_error", error=str(e), next_retry=retry_delay)
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_delay)

    async def _execute_task(self, task_id: str):
        """Execute a single task using the ReAct pattern."""
        logger.info("runner.executing_task", task_id=task_id)
        # Safety: clear any leaked component state
        self._pending_components.clear()
        try:
            # 1. Transition task to 'doing'
            await self.client.move_task(task_id, "doing")

            # 2. Fetch full task details
            task = await self.client.get_task(task_id)
            stream_id = task.session_id or task_id

            await self._emit_stream_event(stream_id, "phase_start", {"phase": "context_inject"})

            # 3. Get latest context injection (routes through Core to Keeper)
            context_summary = await self.client.get_context(
                self.config.id,
                task.description or task.title,
                session_id=task.session_id,
            )

            await self._emit_stream_event(stream_id, "phase_end", {"phase": "context_inject", "duration_ms": 0})

            system_prompt = self._assemble_system_prompt(context_summary)
            messages = [{"role": "user", "content": task.input}]

            # Circuit breaker check
            if self._model_circuit_open:
                elapsed = time.monotonic() - (self._circuit_tripped_at or 0)
                if elapsed > CIRCUIT_HALF_OPEN_AFTER:
                    logger.info(
                        "runner.model_circuit_half_open",
                        agent_id=self.config.id,
                        reason=self._circuit_open_reason,
                        elapsed_seconds=int(elapsed),
                    )
                    # Allow exactly one probe through — normal execution continues
                else:
                    await self._emit_stream_event(
                        stream_id,
                        "model_error",
                        {"category": "circuit_open", "reason": self._circuit_open_reason},
                    )
                    await self.client.complete_task(
                        task_id,
                        f"Agent model unavailable: {self._circuit_open_reason}. Please try again in a few minutes.",
                        status="failed",
                    )
                    return

            turn_number = 0
            while True:
                turn_number += 1
                logger.info("runner.turn_start", task_id=task_id, turn=turn_number)
                await self._emit_stream_event(
                    stream_id,
                    "turn_start",
                    {"turn_number": turn_number, "model": self.config.model_id, "estimated_tokens": len(str(messages)) // 4},
                )

                # 4. LLM Completion via LiteLLM
                completion_kwargs: dict[str, Any] = {
                    "model": f"{_normalize_provider(self.config.model_provider or '')}/{self.config.model_id}",
                    "messages": [{"role": "system", "content": system_prompt}] + messages,
                    "tools": self.tool_definitions if self.tool_definitions else None,
                    "timeout": self.config.config.get("litellm_timeout", 120) if self.config.config else 120,
                }
                if self.config.api_key:
                    completion_kwargs["api_key"] = self.config.api_key
                    # Fallback for some LiteLLM versions/providers that prefer env vars
                    import os
                    if _normalize_provider(self.config.model_provider) == "gemini":
                        os.environ["GEMINI_API_KEY"] = self.config.api_key
                response = await self._model_with_fallback(completion_kwargs, turn_label=f"task:{task_id}")

                # Record cost usage back to Core
                try:
                    usage_payload = {
                        "input_tokens": getattr(response.usage, "prompt_tokens", 0),
                        "output_tokens": getattr(response.usage, "completion_tokens", 0),
                        "reasoning_tokens": getattr(response.usage, "reasoning_tokens", 0),
                        "model_id": self.config.model_id or "unknown",
                        "task_id": task_id,
                        "tier": self.config.config.get("tier", "standard") if self.config.config else "standard",
                    }
                    await self.client.report_usage(self.config.id, usage_payload)
                    await self._emit_stream_event(
                        stream_id,
                        "cost_report",
                        {
                            "input_tokens": usage_payload["input_tokens"],
                            "output_tokens": usage_payload["output_tokens"],
                            "reasoning_tokens": usage_payload["reasoning_tokens"],
                            "model_id": self.config.model_id or "unknown",
                        },
                    )
                except Exception as e:
                    logger.warning("runner.usage_report_failed", agent_id=self.config.id, error=str(e))

                choice = response.choices[0]
                message = choice.message

                # Extract tool calls (OpenAI format or XML fallback)
                tool_calls = self._extract_tool_calls(message)

                # Convert message to dict for storage
                msg_dict = message.model_dump(exclude_none=True)
                # LiteLLM/Gemini schema cleanup
                if "function_call" in msg_dict:
                    del msg_dict["function_call"]

                # If we extracted XML tool calls, inject them into the message dict
                # so the conversation history remains valid for LiteLLM replay.
                xml_extracted = bool(tool_calls) and not getattr(message, "tool_calls", None)
                if xml_extracted:
                    msg_dict["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ]
                    # Strip tool call markup from stored content to keep history clean
                    msg_dict["content"] = self._strip_tool_calls(
                        msg_dict.get("content", "")
                    )
                elif "tool_calls" in msg_dict and not msg_dict["tool_calls"]:
                    del msg_dict["tool_calls"]

                messages.append(msg_dict)

                if not tool_calls:
                    # Final response received
                    # Close circuit if this was a half-open probe, and reset auth counter
                    if self._model_circuit_open:
                        logger.info(
                            "runner.model_circuit_closed",
                            agent_id=self.config.id,
                            reason=self._circuit_open_reason,
                        )
                        self._model_circuit_open = False
                        self._circuit_open_reason = None
                        self._circuit_tripped_at = None
                        self._consecutive_auth_failures = 0
                        try:
                            await self.client.report_model_recovery(self.config.id)
                        except Exception as e:
                            logger.warning("runner.model_recovery_report_failed", error=str(e))
                    self._consecutive_auth_failures = 0

                    clean_content = self._strip_tool_calls(message.content or "")
                    await self._stream_text(stream_id, clean_content)
                    await self.client.complete_task(task_id, clean_content)
                    logger.info("runner.task_success", task_id=task_id)
                    break

                # 5. Handle Tool Execution
                # CHECKPOINT 1: Pre-Execution (As required by Plan Phase 4)
                await self._emit_stream_event(stream_id, "phase_start", {"phase": "checkpoint"})
                await self.client.save_checkpoint(
                    task_id,
                    turn_number,
                    messages,
                    tool_calls=[
                        {"id": tc.id, "type": tc.type, "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                        for tc in tool_calls
                    ],
                )
                await self._emit_stream_event(stream_id, "phase_end", {"phase": "checkpoint", "duration_ms": 0})

                for tool_call in tool_calls:
                    tool_name = tool_call.function.name
                    args_data = tool_call.function.arguments

                    if isinstance(args_data, str):
                        tool_args = json.loads(args_data)
                    elif isinstance(args_data, dict):
                        tool_args = args_data
                    else:
                        tool_args = {}  # fallback for None or unexpected types

                    await self._emit_stream_event(
                        stream_id,
                        "tool_call",
                        {"tool": tool_name, "args": tool_args, "status": "started"},
                    )
                    logger.info("runner.invoking_tool", tool=tool_name, args=tool_args)
                    tool_start = time.monotonic()
                    result = await self._execute_tool(tool_name, tool_args, session_id=stream_id)
                    tool_duration_ms = round((time.monotonic() - tool_start) * 1000, 2)
                    await self._emit_stream_event(
                        stream_id,
                        "tool_call",
                        {
                            "tool": tool_name,
                            "status": "done",
                            "result_summary": str(result)[:200],
                            "duration_ms": tool_duration_ms,
                        },
                    )

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": result,
                    })

                await self._emit_stream_event(
                    stream_id,
                    "turn_end",
                    {"turn_number": turn_number},
                )

                # CHECKPOINT 2: Post-Execution (As required by Plan Phase 4)
                await self.client.save_checkpoint(task_id, turn_number, messages)

        except Exception as e:
            category, user_message = _classify_model_error(e)
            logger.error(
                "runner.task_model_error",
                task_id=task_id,
                category=category.value,
                error=str(e),
            )
            self._pending_components.clear()

            # Trip circuit on sustained auth failures
            if category == ModelErrorCategory.AUTH:
                self._consecutive_auth_failures += 1
                if self._consecutive_auth_failures >= 3 and not self._model_circuit_open:
                    self._model_circuit_open = True
                    self._circuit_open_reason = f"auth_error ({self.config.model_provider}/{self.config.model_id})"
                    self._circuit_tripped_at = time.monotonic()
                    logger.error(
                        "runner.model_circuit_tripped",
                        agent_id=self.config.id,
                        reason=self._circuit_open_reason,
                        consecutive_failures=self._consecutive_auth_failures,
                    )
                    try:
                        await self.client.report_model_error(
                            self.config.id,
                            category="auth_error",
                            reason=self._circuit_open_reason,
                        )
                    except Exception as report_err:
                        logger.warning("runner.model_error_report_failed", error=str(report_err))

            await self.client.complete_task(task_id, user_message, status="failed")

    async def _execute_session_message(self, payload: dict):
        """Execute a session message using the ReAct pattern."""
        session_id = payload.get("session_id")
        if session_id in self._inflight_sessions:
            logger.warning(
                "runner.session_already_inflight",
                session_id=session_id,
                reason="duplicate_session_message_event",
            )
            return
        logger.info("runner.executing_session_message", session_id=session_id)
        self._inflight_sessions.add(session_id)
        # Safety: clear any leaked component state from a prior interrupted turn
        self._pending_components.clear()
        try:
            context_summary = payload.get("context_summary") or ""
            await self._emit_stream_event(session_id, "phase_start", {"phase": "context_inject"})
            session_info = {
                "user_id": payload.get("user_id"),
                "channel": payload.get("channel"),
                "session_id": session_id,
            }
            system_prompt = self._assemble_system_prompt(context_summary, session_info)
            await self._emit_stream_event(session_id, "phase_end", {"phase": "context_inject", "duration_ms": 0})

            # Circuit breaker check
            if self._model_circuit_open:
                elapsed = time.monotonic() - (self._circuit_tripped_at or 0)
                if elapsed > CIRCUIT_HALF_OPEN_AFTER:
                    logger.info(
                        "runner.model_circuit_half_open",
                        agent_id=self.config.id,
                        reason=self._circuit_open_reason,
                        elapsed_seconds=int(elapsed),
                    )
                    # Allow exactly one probe through — normal execution continues
                else:
                    await self._emit_stream_event(
                        session_id,
                        "model_error",
                        {"category": "circuit_open", "reason": self._circuit_open_reason},
                    )
                    try:
                        await self.client.reply_to_session(
                            session_id,
                            f"Agent model unavailable: {self._circuit_open_reason}. Please try again in a few minutes.",
                        )
                    except Exception as reply_err:
                        logger.error("runner.session_reply_failed", session_id=session_id, error=str(reply_err))
                    return

            # Start with existing session messages
            raw_messages = list(payload.get("messages", []))
            messages = []
            for msg in raw_messages:
                if msg.get("role") == "user" and msg.get("type") == "action" and not msg.get("content"):
                    action_text = f"User action: {msg.get('action_type', 'unknown')} on {msg.get('action_id', 'unknown')}"
                    if msg.get("payload"):
                        action_text += f"\nPayload: {json.dumps(msg['payload'])}"
                    messages.append({
                        "role": "user",
                        "content": action_text,
                    })
                else:
                    messages.append(msg)

            turn_number = 0
            while True:
                turn_number += 1
                logger.info(
                    "runner.turn_start", session_id=session_id, turn=turn_number
                )
                await self._emit_stream_event(
                    session_id,
                    "turn_start",
                    {
                        "turn_number": turn_number,
                        "model": self.config.model_id,
                        "estimated_tokens": len(str(messages)) // 4,
                    },
                )

                completion_kwargs = {
                    "model": f"{_normalize_provider(self.config.model_provider or '')}/{self.config.model_id}",
                    "messages": [{"role": "system", "content": system_prompt}] + messages,
                    "tools": self.tool_definitions if self.tool_definitions else None,
                    "timeout": self.config.config.get("litellm_timeout", 120) if self.config.config else 120,
                }

                # Debug: emit truncated prompt preview (Mode D)
                prompt_preview = json.dumps(completion_kwargs.get("messages", []))[:2000]
                await self._emit_stream_event(
                    session_id,
                    "debug_prompt",
                    {"prompt_preview": prompt_preview, "token_count": len(str(completion_kwargs.get("messages", []))) // 4},
                )

                if self.config.api_key:
                    completion_kwargs["api_key"] = self.config.api_key
                    # Fallback for some LiteLLM versions/providers that prefer env vars
                    import os
                    if _normalize_provider(self.config.model_provider) == "gemini":
                        os.environ["GEMINI_API_KEY"] = self.config.api_key
                response = await self._model_with_fallback(completion_kwargs, turn_label=f"session:{session_id}")

                # Record cost usage back to Core
                try:
                    usage_payload = {
                        "input_tokens": getattr(response.usage, "prompt_tokens", 0),
                        "output_tokens": getattr(response.usage, "completion_tokens", 0),
                        "reasoning_tokens": getattr(response.usage, "reasoning_tokens", 0),
                        "model_id": self.config.model_id or "unknown",
                        "task_id": None,
                        "tier": self.config.config.get("tier", "standard") if self.config.config else "standard",
                    }
                    await self.client.report_usage(self.config.id, usage_payload)
                    # Emit cost report for trace/debug modes
                    await self._emit_stream_event(
                        session_id,
                        "cost_report",
                        {
                            "input_tokens": usage_payload["input_tokens"],
                            "output_tokens": usage_payload["output_tokens"],
                            "reasoning_tokens": usage_payload["reasoning_tokens"],
                            "model_id": self.config.model_id or "unknown",
                        },
                    )
                except Exception as e:
                    logger.warning("runner.usage_report_failed", agent_id=self.config.id, error=str(e))

                choice = response.choices[0]
                message = choice.message

                # Debug: emit truncated response preview (Mode D)
                response_preview = str(message.content or "")[:2000]
                await self._emit_stream_event(
                    session_id,
                    "debug_response",
                    {"response_preview": response_preview, "token_count": len(str(message.content or "")) // 4},
                )

                # Extract tool calls (OpenAI format or XML fallback)
                tool_calls = self._extract_tool_calls(message)

                msg_dict = message.model_dump(exclude_none=True)
                # LiteLLM/Gemini schema cleanup
                if "function_call" in msg_dict:
                    del msg_dict["function_call"]

                # If we extracted XML tool calls, inject them into the message dict
                xml_extracted = bool(tool_calls) and not getattr(message, "tool_calls", None)
                if xml_extracted:
                    msg_dict["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ]
                    msg_dict["content"] = self._strip_tool_calls(
                        msg_dict.get("content", "")
                    )
                elif "tool_calls" in msg_dict and not msg_dict["tool_calls"]:
                    del msg_dict["tool_calls"]

                messages.append(msg_dict)

                if not tool_calls:
                    # Final response received
                    # Close circuit if this was a half-open probe, and reset auth counter
                    if self._model_circuit_open:
                        logger.info(
                            "runner.model_circuit_closed",
                            agent_id=self.config.id,
                            reason=self._circuit_open_reason,
                        )
                        self._model_circuit_open = False
                        self._circuit_open_reason = None
                        self._circuit_tripped_at = None
                        self._consecutive_auth_failures = 0
                        try:
                            await self.client.report_model_recovery(self.config.id)
                        except Exception as e:
                            logger.warning("runner.model_recovery_report_failed", error=str(e))
                    self._consecutive_auth_failures = 0

                    final_text = self._strip_tool_calls(message.content or "")
                    components = list(self._pending_components)
                    self._pending_components.clear()
                    # Attach any audio generated by text_to_speech this turn
                    pending_audio = self._pending_audio.pop(session_id, None)
                    # Stream the final text before sending the formal reply
                    await self._stream_text(session_id, final_text)
                    try:
                        await self.client.reply_to_session(
                            session_id,
                            final_text,
                            components=components,
                            audio_b64=pending_audio.get("audio_b64") if pending_audio else None,
                            audio_voice=pending_audio.get("voice") if pending_audio else None,
                        )
                        logger.info(
                            "runner.session_reply_sent",
                            session_id=session_id,
                            component_count=len(components),
                            has_audio=bool(pending_audio),
                        )
                    except Exception as e:
                        logger.error(
                            "runner.session_reply_failed",
                            session_id=session_id,
                            error=str(e),
                        )
                    break

                # Handle Tool Execution
                for tool_call in tool_calls:
                    tool_name = tool_call.function.name
                    args_data = tool_call.function.arguments

                    if isinstance(args_data, str):
                        tool_args = json.loads(args_data)
                    elif isinstance(args_data, dict):
                        tool_args = args_data
                    else:
                        tool_args = {}  # fallback for None or unexpected types

                    await self._emit_stream_event(
                        session_id,
                        "tool_call",
                        {"tool": tool_name, "args": tool_args, "status": "started"},
                    )
                    logger.info(
                        "runner.invoking_tool", tool=tool_name, args=tool_args
                    )
                    tool_start = time.monotonic()
                    result = await self._execute_tool(tool_name, tool_args, session_id=session_id)
                    tool_duration_ms = round((time.monotonic() - tool_start) * 1000, 2)
                    await self._emit_stream_event(
                        session_id,
                        "tool_call",
                        {
                            "tool": tool_name,
                            "status": "done",
                            "result_summary": str(result)[:200],
                            "duration_ms": tool_duration_ms,
                        },
                    )

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": result,
                    })

                # End of turn
                await self._emit_stream_event(
                    session_id,
                    "turn_end",
                    {"turn_number": turn_number},
                )

        except Exception as e:
            category, user_message = _classify_model_error(e)
            logger.error(
                "runner.session_model_error",
                session_id=session_id,
                category=category.value,
                error=str(e),
            )
            self._pending_components.clear()

            # Trip circuit on sustained auth failures
            if category == ModelErrorCategory.AUTH:
                self._consecutive_auth_failures += 1
                if self._consecutive_auth_failures >= 3 and not self._model_circuit_open:
                    self._model_circuit_open = True
                    self._circuit_open_reason = f"auth_error ({self.config.model_provider}/{self.config.model_id})"
                    self._circuit_tripped_at = time.monotonic()
                    logger.error(
                        "runner.model_circuit_tripped",
                        agent_id=self.config.id,
                        reason=self._circuit_open_reason,
                        consecutive_failures=self._consecutive_auth_failures,
                    )
                    try:
                        await self.client.report_model_error(
                            self.config.id,
                            category="auth_error",
                            reason=self._circuit_open_reason,
                        )
                    except Exception as report_err:
                        logger.warning("runner.model_error_report_failed", error=str(report_err))

            try:
                await self.client.reply_to_session(session_id, user_message)
            except Exception as reply_err:
                logger.error(
                    "runner.session_reply_failed",
                    session_id=session_id,
                    error=str(reply_err),
                )
        finally:
            self._inflight_sessions.discard(session_id)

    async def stop(self):
        """Gracefully stop the agent."""
        self._running = False
        await self.client.close()
