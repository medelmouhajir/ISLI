"""ReAct execution loops for Kanban tasks and session messages."""

import json
import time
from typing import TYPE_CHECKING, Any

import structlog

from ..utils.tokens import count_message_tokens
from .constants import CIRCUIT_HALF_OPEN_AFTER, MAX_LLM_TURNS, MAX_CONSECUTIVE_TOOL_FAILURES
from .errors import ModelErrorCategory, _classify_model_error
from .parsing import _ParsedToolCall

if TYPE_CHECKING:
    from .core import AgentRunner

logger = structlog.get_logger()


class ReActLoop:
    """Runs the think-act-observe ReAct loop for tasks and chat sessions."""

    def __init__(self, runner: "AgentRunner"):
        self.runner = runner

    def _extract_and_normalize_tool_calls(self, message) -> tuple[list[_ParsedToolCall], dict, bool]:
        """Extract tool calls from a model message and normalize the message dict.

        Returns (tool_calls, msg_dict, xml_extracted).
        """
        tool_calls = self.runner._extract_tool_calls(message)

        # Convert message to dict for storage
        msg_dict = message.model_dump(exclude_none=True)
        # LiteLLM/Gemini schema cleanup
        if "function_call" in msg_dict:
            del msg_dict["function_call"]

        # If we extracted XML/JSON/legacy tool calls, inject them into the message dict
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
            msg_dict["content"] = self.runner._strip_tool_calls(
                msg_dict.get("content", "")
            )
        elif "tool_calls" in msg_dict and not msg_dict["tool_calls"]:
            del msg_dict["tool_calls"]

        return tool_calls, msg_dict, xml_extracted

    async def _execute_tools(
        self,
        tool_calls: list[_ParsedToolCall],
        messages: list[dict],
        stream_id: str,
        consecutive_tool_failures: int,
        is_task: bool,
        task_or_session_id: str,
    ) -> int:
        """Execute all tool calls for a turn and append results to messages.

        Returns the updated consecutive_tool_failures count. On excessive failures,
        it terminates the loop by completing the task/session and raising a
        sentinel exception to break out.
        """
        runner = self.runner
        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            args_data = tool_call.function.arguments

            if isinstance(args_data, str):
                tool_args = json.loads(args_data)
            elif isinstance(args_data, dict):
                tool_args = args_data
            else:
                tool_args = {}  # fallback for None or unexpected types

            await runner._streamer.emit_event(
                stream_id,
                "tool_call",
                {"tool": tool_name, "args": tool_args, "status": "started"},
            )
            logger.info("runner.invoking_tool", tool=tool_name, args=tool_args)
            tool_start = time.monotonic()
            result = await runner._tool_engine.execute(tool_name, tool_args, session_id=stream_id)
            tool_duration_ms = round((time.monotonic() - tool_start) * 1000, 2)
            await runner._streamer.emit_event(
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

            if isinstance(result, str) and (result.startswith("Error:") or result.startswith("Validation Error:")):
                consecutive_tool_failures += 1
                if consecutive_tool_failures >= MAX_CONSECUTIVE_TOOL_FAILURES:
                    logger.error("runner.tool_failures_exceeded", task_or_session_id=task_or_session_id, tool=tool_name)
                    if is_task:
                        await runner.client.complete_task(
                            task_or_session_id,
                            f"Task exceeded maximum consecutive tool failures ({MAX_CONSECUTIVE_TOOL_FAILURES}). Last error: {str(result)[:200]}",
                            status="failed",
                        )
                    else:
                        final_text = f"I'm repeatedly failing to execute a required action (tool: {tool_name}). Let's stop here so you can review."
                        await runner._streamer.emit_event(stream_id, "token_delta", {"text": final_text})
                        await runner.client.reply_to_session(stream_id, final_text)
                    raise _LoopTerminated()
            else:
                consecutive_tool_failures = 0

        # If discover_skills was invoked, expand tool set for the next iteration
        if any(tc.function.name == "discover_skills" for tc in tool_calls):
            logger.info("runner.discover_skills_triggered", stream_id=stream_id)
            runner._expand_tools_next_iteration = True

        return consecutive_tool_failures

    async def _report_usage(self, response, stream_id: str, task_id: str | None):
        """Report token usage back to Core and emit a cost stream event."""
        runner = self.runner
        try:
            usage_payload = {
                "input_tokens": getattr(response.usage, "prompt_tokens", 0),
                "output_tokens": getattr(response.usage, "completion_tokens", 0),
                "reasoning_tokens": getattr(response.usage, "reasoning_tokens", 0),
                "model_id": runner.config.model_id or "unknown",
                "task_id": task_id,
                "tier": runner.config.config.get("tier", "standard") if runner.config.config else "standard",
            }
            await runner.client.report_usage(runner.config.id, usage_payload)
            await runner._streamer.emit_event(
                stream_id,
                "cost_report",
                {
                    "input_tokens": usage_payload["input_tokens"],
                    "output_tokens": usage_payload["output_tokens"],
                    "reasoning_tokens": usage_payload["reasoning_tokens"],
                    "model_id": runner.config.model_id or "unknown",
                },
            )
        except Exception as e:
            logger.warning("runner.usage_report_failed", agent_id=runner.config.id, error=str(e))

    async def execute_task(self, task_data: dict):
        """Execute a single task using the ReAct pattern.

        ``task_data`` is the full task payload from the WebSocket ``task:updated``
        event, which already includes ``context_summary`` inline.  No extra HTTP
        calls to Core are required.
        """
        runner = self.runner
        task_id = task_data["id"]
        logger.info("runner.executing_task", task_id=task_id)
        # Safety: clear any leaked component state
        runner._pending_components.clear()
        try:
            # 1. Transition task to 'doing'
            await runner.client.move_task(task_id, "doing")

            stream_id = task_data.get("session_id") or task_id

            await runner._streamer.emit_event(stream_id, "phase_start", {"phase": "context_inject"})

            # 2. Read context_summary inline from the WebSocket payload
            context_summary = task_data.get("context_summary") or ""
            relevant_skills = task_data.get("relevant_skills")

            await runner._streamer.emit_event(stream_id, "phase_end", {"phase": "context_inject", "duration_ms": 0})

            # Per-turn tool filtering; reset expansion flag at task start
            runner._active_tool_definitions = runner._tool_engine.filter_by_relevance(relevant_skills)
            runner._expand_tools_next_iteration = False

            system_prompt = runner._prompt_assembler.assemble(
                context_summary, relevant_skills=relevant_skills, task_mode=True
            )
            messages = [{"role": "user", "content": task_data.get("input", "")}]

            # PII Mesh: anonymize before LLM
            stream_id = task_data.get("session_id") or task_id
            system_prompt, messages = await runner._pii_manager.prepare_llm_payload(system_prompt, messages, stream_id)

            # Circuit breaker check
            if runner._model_circuit_open:
                elapsed = time.monotonic() - (runner._circuit_tripped_at or 0)
                if elapsed > CIRCUIT_HALF_OPEN_AFTER:
                    logger.info(
                        "runner.model_circuit_half_open",
                        agent_id=runner.config.id,
                        reason=runner._circuit_open_reason,
                        elapsed_seconds=int(elapsed),
                    )
                    # Allow exactly one probe through — normal execution continues
                else:
                    await runner._streamer.emit_event(
                        stream_id,
                        "model_error",
                        {"category": "circuit_open", "reason": runner._circuit_open_reason},
                    )
                    await runner.client.complete_task(
                        task_id,
                        f"Agent model unavailable: {runner._circuit_open_reason}. Please try again in a few minutes.",
                        status="failed",
                    )
                    return

            turn_number = 0
            consecutive_tool_failures = 0
            while True:
                turn_number += 1
                if turn_number > MAX_LLM_TURNS:
                    logger.warning("runner.max_turns_exceeded", task_id=task_id, turns=turn_number)
                    await runner.client.complete_task(
                        task_id,
                        f"Task exceeded maximum allowed LLM turns ({MAX_LLM_TURNS}).",
                        status="failed",
                    )
                    return
                logger.info("runner.turn_start", task_id=task_id, turn=turn_number)
                await runner._streamer.emit_event(
                    stream_id,
                    "turn_start",
                    {"turn_number": turn_number, "model": runner.config.model_id, "estimated_tokens": count_message_tokens(messages)},
                )

                # 4. LLM Completion via LiteLLM
                # Apply per-turn token cap truncation
                messages = runner._model_client.truncate_tool_results_to_cap(messages, max_tokens=1000)

                # If discover_skills was called last turn, expand tool set for this turn
                if runner._expand_tools_next_iteration:
                    logger.info("runner.expanding_tools_after_discovery", task_id=task_id)
                    runner._active_tool_definitions = runner._all_tool_definitions
                    runner._expand_tools_next_iteration = False

                completion_kwargs: dict[str, Any] = {
                    "model": runner._model_client.resolve_model(),
                    "messages": [{"role": "system", "content": system_prompt}] + messages,
                    "tools": runner._active_tool_definitions if runner._active_tool_definitions else None,
                    "timeout": runner.config.config.get("litellm_timeout", 120) if runner.config.config else 120,
                }
                runner._model_client.apply_auth_to_kwargs(completion_kwargs)
                await runner._streamer.emit_event(
                    stream_id,
                    "phase_start",
                    {"phase": "llm_inference", "label": "THINKING...", "turn": turn_number},
                )
                response = await runner._model_client.model_with_fallback(completion_kwargs, turn_label=f"task:{task_id}")
                await runner._streamer.emit_event(
                    stream_id,
                    "phase_end",
                    {"phase": "llm_inference", "turn": turn_number},
                )

                # Record cost usage back to Core
                await self._report_usage(response, stream_id, task_id)

                choice = response.choices[0]
                message = choice.message

                # Extract tool calls (OpenAI format or XML fallback)
                tool_calls, msg_dict, xml_extracted = self._extract_and_normalize_tool_calls(message)
                messages.append(msg_dict)

                if not tool_calls:
                    # Final response received
                    # Close circuit if this was a half-open probe, and reset auth counter
                    if runner._model_circuit_open:
                        logger.info(
                            "runner.model_circuit_closed",
                            agent_id=runner.config.id,
                            reason=runner._circuit_open_reason,
                        )
                        runner._model_circuit_open = False
                        runner._circuit_open_reason = None
                        runner._circuit_tripped_at = None
                        runner._consecutive_auth_failures = 0
                        try:
                            await runner.client.report_model_recovery(runner.config.id)
                        except Exception as e:
                            logger.warning("runner.model_recovery_report_failed", error=str(e))
                    runner._consecutive_auth_failures = 0

                    clean_content = runner._strip_tool_calls(message.content or "")
                    if not clean_content and any(m.get("role") == "tool" for m in messages):
                        clean_content = runner._prompt_assembler.build_tool_fallback_summary(messages)
                        logger.warning(
                            "runner.empty_final_response_fallback",
                            task_id=task_id,
                            fallback_used=True,
                            fallback_length=len(clean_content),
                        )
                    clean_content = runner._pii_manager.post_process_response(clean_content, stream_id)
                    await runner._streamer.stream_text(stream_id, clean_content)
                    await runner.client.complete_task(task_id, clean_content)
                    logger.info("runner.task_success", task_id=task_id)
                    break

                # 5. Handle Tool Execution
                # CHECKPOINT 1: Pre-Execution (As required by Plan Phase 4)
                await runner._streamer.emit_event(stream_id, "phase_start", {"phase": "checkpoint"})
                await runner.client.save_checkpoint(
                    task_id,
                    turn_number,
                    messages,
                    tool_calls=[
                        {"id": tc.id, "type": tc.type, "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                        for tc in tool_calls
                    ],
                )
                await runner._streamer.emit_event(stream_id, "phase_end", {"phase": "checkpoint", "duration_ms": 0})

                try:
                    consecutive_tool_failures = await self._execute_tools(
                        tool_calls,
                        messages,
                        stream_id,
                        consecutive_tool_failures,
                        is_task=True,
                        task_or_session_id=task_id,
                    )
                except _LoopTerminated:
                    return

                await runner._streamer.emit_event(
                    stream_id,
                    "turn_end",
                    {"turn_number": turn_number},
                )

                # CHECKPOINT 2: Post-Execution (As required by Plan Phase 4)
                await runner.client.save_checkpoint(task_id, turn_number, messages)

            # Drain-and-swap: reload tool registry between turns if a skill was updated
            if runner._pending_tool_reload:
                logger.info("runner.tool_reload_after_task", task_id=task_id)
                await runner._tool_engine.auto_register_from_skills()
                runner._pending_tool_reload = False

        except Exception as e:
            category, user_message = _classify_model_error(e)
            logger.error(
                "runner.task_model_error",
                task_id=task_id,
                category=category.value,
                error=str(e),
            )
            runner._pending_components.clear()

            # Trip circuit on sustained auth failures
            if category == ModelErrorCategory.AUTH:
                runner._consecutive_auth_failures += 1
                if runner._consecutive_auth_failures >= 3 and not runner._model_circuit_open:
                    runner._model_circuit_open = True
                    runner._circuit_open_reason = f"auth_error ({runner.config.model_provider}/{runner.config.model_id})"
                    runner._circuit_tripped_at = time.monotonic()
                    logger.error(
                        "runner.model_circuit_tripped",
                        agent_id=runner.config.id,
                        reason=runner._circuit_open_reason,
                        consecutive_failures=runner._consecutive_auth_failures,
                    )
                    try:
                        await runner.client.report_model_error(
                            runner.config.id,
                            category="auth_error",
                            reason=runner._circuit_open_reason,
                        )
                    except Exception as report_err:
                        logger.warning("runner.model_error_report_failed", error=str(report_err))

            await runner.client.complete_task(task_id, user_message, status="failed")

    async def execute_session_message(self, payload: dict):
        """Execute a session message using the ReAct pattern."""
        from typing import cast
        runner = self.runner
        session_id_raw = payload.get("session_id")
        if not session_id_raw:
            logger.error("runner.session_missing_id", payload=payload)
            return
        session_id = cast(str, session_id_raw)
        if session_id in runner._inflight_sessions:
            logger.warning(
                "runner.session_already_inflight",
                session_id=session_id,
                reason="duplicate_session_message_event",
            )
            return
        logger.info("runner.executing_session_message", session_id=session_id)
        runner._inflight_sessions.add(session_id)
        # Safety: clear any leaked component state from a prior interrupted turn
        runner._pending_components.clear()
        runner._pending_attachments.pop(session_id, None)
        try:
            context_summary = payload.get("context_summary") or ""
            relevant_skills = payload.get("relevant_skills")
            await runner._streamer.emit_event(session_id, "phase_start", {"phase": "context_inject"})
            session_info = {
                "user_id": payload.get("user_id"),
                "channel": payload.get("channel"),
                "session_id": session_id,
                "room_id": payload.get("room_id"),
            }

            # Per-turn tool filtering; reset expansion flag at session start
            runner._active_tool_definitions = runner._tool_engine.filter_by_relevance(relevant_skills)
            runner._expand_tools_next_iteration = False

            system_prompt = runner._prompt_assembler.assemble(context_summary, session_info, relevant_skills=relevant_skills)
            await runner._streamer.emit_event(session_id, "phase_end", {"phase": "context_inject", "duration_ms": 0})

            # Circuit breaker check
            if runner._model_circuit_open:
                elapsed = time.monotonic() - (runner._circuit_tripped_at or 0)
                if elapsed > CIRCUIT_HALF_OPEN_AFTER:
                    logger.info(
                        "runner.model_circuit_half_open",
                        agent_id=runner.config.id,
                        reason=runner._circuit_open_reason,
                        elapsed_seconds=int(elapsed),
                    )
                    # Allow exactly one probe through — normal execution continues
                else:
                    await runner._streamer.emit_event(
                        session_id,
                        "model_error",
                        {"category": "circuit_open", "reason": runner._circuit_open_reason},
                    )
                    try:
                        await runner.client.reply_to_session(
                            session_id,
                            f"Agent model unavailable: {runner._circuit_open_reason}. Please try again in a few minutes.",
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

            # PII Mesh: anonymize before LLM
            system_prompt, messages = await runner._pii_manager.prepare_llm_payload(
                system_prompt, messages, session_id
            )

            turn_number = 0
            consecutive_tool_failures = 0
            while True:
                turn_number += 1
                if turn_number > MAX_LLM_TURNS:
                    logger.warning("runner.max_turns_exceeded", session_id=session_id, turns=turn_number)
                    final_text = "I've encountered an issue completing this request (exceeded maximum turns). Let's pause here."
                    await runner._streamer.emit_event(
                        session_id,
                        "token_delta",
                        {"text": final_text},
                    )
                    await runner.client.reply_to_session(
                        session_id, final_text, components=list(runner._pending_components)
                    )
                    return
                logger.info(
                    "runner.turn_start", session_id=session_id, turn=turn_number
                )
                await runner._streamer.emit_event(
                    session_id,
                    "turn_start",
                    {
                        "turn_number": turn_number,
                        "model": runner.config.model_id,
                        "estimated_tokens": count_message_tokens(messages),
                    },
                )

                # Apply per-turn token cap truncation
                messages = runner._model_client.truncate_tool_results_to_cap(messages, max_tokens=1000)

                # If discover_skills was called last turn, expand tool set for this turn
                if runner._expand_tools_next_iteration:
                    logger.info("runner.expanding_tools_after_discovery", session_id=session_id)
                    runner._active_tool_definitions = runner._all_tool_definitions
                    runner._expand_tools_next_iteration = False

                completion_kwargs = {
                    "model": runner._model_client.resolve_model(),
                    "messages": [{"role": "system", "content": system_prompt}] + messages,
                    "tools": runner._active_tool_definitions if runner._active_tool_definitions else None,
                    "timeout": runner.config.config.get("litellm_timeout", 120) if runner.config.config else 120,
                }

                # Debug: emit truncated prompt preview (Mode D)
                prompt_preview = json.dumps(completion_kwargs.get("messages", []))[:2000]
                await runner._streamer.emit_event(
                    session_id,
                    "debug_prompt",
                    {"prompt_preview": prompt_preview, "token_count": len(str(completion_kwargs.get("messages", []))) // 4},
                )

                runner._model_client.apply_auth_to_kwargs(completion_kwargs)
                await runner._streamer.emit_event(
                    session_id,
                    "phase_start",
                    {"phase": "llm_inference", "label": "THINKING...", "turn": turn_number},
                )
                response = await runner._model_client.model_with_fallback(completion_kwargs, turn_label=f"session:{session_id}")
                await runner._streamer.emit_event(
                    session_id,
                    "phase_end",
                    {"phase": "llm_inference", "turn": turn_number},
                )

                # Record cost usage back to Core
                await self._report_usage(response, session_id, None)

                choice = response.choices[0]
                message = choice.message

                # Debug: emit truncated response preview (Mode D)
                response_preview = str(message.content or "")[:2000]
                await runner._streamer.emit_event(
                    session_id,
                    "debug_response",
                    {"response_preview": response_preview, "token_count": len(str(message.content or "")) // 4},
                )

                # Extract tool calls (OpenAI format or XML fallback)
                tool_calls, msg_dict, xml_extracted = self._extract_and_normalize_tool_calls(message)
                messages.append(msg_dict)

                if not tool_calls:
                    # Final response received
                    # Close circuit if this was a half-open probe, and reset auth counter
                    if runner._model_circuit_open:
                        logger.info(
                            "runner.model_circuit_closed",
                            agent_id=runner.config.id,
                            reason=runner._circuit_open_reason,
                        )
                        runner._model_circuit_open = False
                        runner._circuit_open_reason = None
                        runner._circuit_tripped_at = None
                        runner._consecutive_auth_failures = 0
                        try:
                            await runner.client.report_model_recovery(runner.config.id)
                        except Exception as e:
                            logger.warning("runner.model_recovery_report_failed", error=str(e))
                    runner._consecutive_auth_failures = 0

                    final_text = runner._strip_tool_calls(message.content or "")
                    if not final_text and any(m.get("role") == "tool" for m in messages):
                        final_text = runner._prompt_assembler.build_tool_fallback_summary(messages)
                        logger.warning(
                            "runner.empty_final_response_fallback",
                            session_id=session_id,
                            fallback_used=True,
                            fallback_length=len(final_text),
                        )
                    final_text = runner._pii_manager.post_process_response(final_text, session_id)
                    components = list(runner._pending_components)
                    runner._pending_components.clear()
                    # Attach any audio generated by text_to_speech this turn
                    pending_audio = runner._pending_audio.pop(session_id, None)
                    # Attach any files staged for this session reply
                    pending_attachments = runner._pending_attachments.pop(session_id, None)
                    # Stream the final text before sending the formal reply
                    await runner._streamer.stream_text(session_id, final_text)
                    try:
                        await runner.client.reply_to_session(
                            session_id,
                            final_text,
                            components=components,
                            audio_b64=pending_audio.get("audio_b64") if pending_audio else None,
                            audio_voice=pending_audio.get("voice") if pending_audio else None,
                            attachments=pending_attachments,
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
                try:
                    consecutive_tool_failures = await self._execute_tools(
                        tool_calls,
                        messages,
                        session_id,
                        consecutive_tool_failures,
                        is_task=False,
                        task_or_session_id=session_id,
                    )
                except _LoopTerminated:
                    return

                await runner._streamer.emit_event(
                    session_id,
                    "turn_end",
                    {"turn_number": turn_number},
                )

            # Drain-and-swap: reload tool registry between turns if a skill was updated
            if runner._pending_tool_reload:
                logger.info("runner.tool_reload_after_session", session_id=session_id)
                await runner._tool_engine.auto_register_from_skills()
                runner._pending_tool_reload = False

        except Exception as e:
            category, user_message = _classify_model_error(e)
            logger.error(
                "runner.session_model_error",
                session_id=session_id,
                category=category.value,
                error=str(e),
            )
            runner._pending_components.clear()

            # Trip circuit on sustained auth failures
            if category == ModelErrorCategory.AUTH:
                runner._consecutive_auth_failures += 1
                if runner._consecutive_auth_failures >= 3 and not runner._model_circuit_open:
                    runner._model_circuit_open = True
                    runner._circuit_open_reason = f"auth_error ({runner.config.model_provider}/{runner.config.model_id})"
                    runner._circuit_tripped_at = time.monotonic()
                    logger.error(
                        "runner.model_circuit_tripped",
                        agent_id=runner.config.id,
                        reason=runner._circuit_open_reason,
                        consecutive_failures=runner._consecutive_auth_failures,
                    )
                    try:
                        await runner.client.report_model_error(
                            runner.config.id,
                            category="auth_error",
                            reason=runner._circuit_open_reason,
                        )
                    except Exception as report_err:
                        logger.warning("runner.model_error_report_failed", error=str(report_err))

            try:
                await runner.client.reply_to_session(session_id, user_message)
            except Exception as reply_err:
                logger.error(
                    "runner.session_reply_failed",
                    session_id=session_id,
                    error=str(reply_err),
                )
        finally:
            runner._inflight_sessions.discard(session_id)
            await runner._lifecycle.notify_session_ready(session_id)


class _LoopTerminated(Exception):
    """Internal sentinel raised when a ReAct loop terminates early (e.g. too many tool failures)."""
    pass
