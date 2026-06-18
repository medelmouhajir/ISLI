"""Streaming event queue, emission, and WebSocket draining."""

import asyncio
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from .core import AgentRunner

logger = structlog.get_logger()


class Streamer:
    """Manages the outgoing event queue and best-effort WebSocket streaming."""

    def __init__(self, runner: "AgentRunner"):
        self.runner = runner
        if not hasattr(runner, "_outgoing_queue"):
            runner._outgoing_queue = asyncio.Queue(maxsize=1000)

    def _resolve_streaming_mode(self, session_id: str) -> str:
        """Resolve streaming mode: session metadata > agent config > silent."""
        if self.runner._current_session_metadata and "streaming_mode" in self.runner._current_session_metadata:
            return self.runner._current_session_metadata["streaming_mode"]
        if self.runner.config.config:
            return self.runner.config.config.get("streaming_mode", "silent")
        return "silent"

    async def emit_event(self, session_id: str, event_type: str, data: dict):
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
                "phase_start",
                "phase_end",
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
                self.runner._outgoing_queue.put_nowait(event)
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

    async def stream_text(self, session_id: str, text: str):
        """Emit token_delta events by splitting text into configurable chunks."""
        cfg = self.runner.config.config or {}
        chunk_size = cfg.get("stream_chunk_size", 5)
        delay_ms = cfg.get("stream_delay_ms", 20)
        if chunk_size < 1:
            chunk_size = 5
        if delay_ms < 0:
            delay_ms = 20

        for i in range(0, len(text), chunk_size):
            chunk = text[i : i + chunk_size]
            await self.emit_event(session_id, "token_delta", {"delta": chunk})
            await asyncio.sleep(delay_ms / 1000)
        await self.emit_event(session_id, "draft_complete", {})

    async def drain_outgoing_queue(self):
        """Drain the outgoing queue to the active WebSocket."""
        while self.runner._running:
            try:
                event = await asyncio.wait_for(self.runner._outgoing_queue.get(), timeout=1.0)
                websocket = self.runner._websocket
                if websocket and getattr(websocket, "open", False):
                    await websocket.send(json.dumps(event))
                    await asyncio.sleep(0.001)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.warning("runner.drain_queue_error", error=str(e))
