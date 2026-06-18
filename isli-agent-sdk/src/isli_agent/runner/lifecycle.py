"""Agent lifecycle: config sync, heartbeat loop, and WebSocket listener."""

import asyncio
import json
from typing import TYPE_CHECKING

import httpx
import websockets

import structlog

from ..models import AgentConfig
from ..tools import DATETIME_DEF, STAGE_REPLY_ATTACHMENT_DEF, discover_skills, DISCOVER_SKILLS_DEF, get_current_datetime, stage_reply_attachment

if TYPE_CHECKING:
    from .core import AgentRunner

logger = structlog.get_logger()


class LifecycleManager:
    """Maintains the agent's heartbeat and WebSocket connection to Core."""

    def __init__(self, runner: "AgentRunner"):
        self.runner = runner

    async def sync_config(self):
        """Dynamically re-sync configuration and reload tools from Core."""
        runner = self.runner
        logger.info("runner.syncing_config", agent_id=runner.config.id)
        try:
            # Re-register to get fresh config (idempotent)
            reg_data = await runner.client.register(runner.config)
            if reg_data:
                logger.debug("runner.sync_config.raw_data", skills=reg_data.get("skills"))
                runner.config = AgentConfig.model_validate(reg_data)

                # Clear existing tools
                runner.tools = {}
                runner.tool_definitions = []

                # Re-register tools
                await runner._tool_engine.auto_register_from_skills()
                runner._tool_engine.add_tool("get_current_datetime", get_current_datetime, DATETIME_DEF)
                runner._tool_engine.add_tool(
                    "stage_reply_attachment", stage_reply_attachment, STAGE_REPLY_ATTACHMENT_DEF
                )

                # Re-snapshot full tool set
                runner._all_tool_definitions = list(runner.tool_definitions)
                runner._active_tool_definitions = list(runner.tool_definitions)

                # discover_skills wrapper reads current list at call time (not capture time)
                def _discover_skills_wrapper():
                    return discover_skills(runner._all_tool_definitions)

                runner._tool_engine.add_tool("discover_skills", _discover_skills_wrapper, DISCOVER_SKILLS_DEF)

                logger.info(
                    "runner.config_reloaded",
                    agent_id=runner.config.id,
                    skills=runner.config.skills,
                    tool_count=len(runner.tools)
                )
        except Exception as e:
            logger.error("runner.sync_config_failed", error=str(e))

    async def heartbeat_loop(self):
        """Background loop to maintain agent's online status."""
        runner = self.runner
        while runner._running:
            try:
                await runner.client.heartbeat(runner.config.id)
                logger.debug("runner.heartbeat_success", agent_id=runner.config.id)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    logger.warning("runner.heartbeat_token_revoked", agent_id=runner.config.id)
                    try:
                        await runner.client.recover_token(runner.config.id)
                        logger.info("runner.token_recovered", agent_id=runner.config.id)
                        # Retry heartbeat immediately with the fresh token
                        await runner.client.heartbeat(runner.config.id)
                        logger.debug("runner.heartbeat_success_after_recovery", agent_id=runner.config.id)
                    except Exception as rec_err:
                        logger.error("runner.token_recovery_failed", agent_id=runner.config.id, error=str(rec_err))
                else:
                    logger.error("runner.heartbeat_failed", agent_id=runner.config.id, error=str(e))
            except Exception as e:
                logger.error("runner.heartbeat_failed", agent_id=runner.config.id, error=str(e))
            await asyncio.sleep(runner.config.heartbeat_interval)

    async def ws_loop(self):
        """WebSocket listener for incoming task assignments."""
        runner = self.runner
        retry_delay = 1.0
        max_delay = 60.0

        while runner._running:
            token = runner.client.token
            if not token:
                await asyncio.sleep(1)
                continue

            ws_url = runner.core_url.replace("http", "ws") + f"/v1/ws/agents/{runner.config.id}"
            try:
                async with websockets.connect(
                    ws_url,
                    additional_headers={"Authorization": f"Bearer {token}"},
                ) as websocket:
                    runner._websocket = websocket
                    logger.info(
                        "runner.ws_connected",
                        url=runner.core_url + f"/v1/ws/agents/{runner.config.id}",
                    )
                    retry_delay = 1.0  # Reset delay on success
                    drain_task = asyncio.create_task(runner._streamer.drain_outgoing_queue())
                    try:
                        async for message in websocket:
                            event = json.loads(message)
                            if event["type"] in ("task:created", "task:updated", "task:moved"):
                                task_data = event["payload"]["task"]
                                if task_data["status"] == "inbox":
                                    logger.info("runner.task_detected", task_id=task_data["id"])
                                    asyncio.create_task(runner._execute_task(task_data))
                            elif event["type"] == "agent:config_updated":
                                logger.info("runner.config_update_event_detected", agent_id=runner.config.id)
                                asyncio.create_task(runner._sync_config())
                            elif event["type"] == "skill:enabled":
                                logger.info(
                                    "runner.skill_enabled_event_detected",
                                    agent_id=runner.config.id,
                                    skill_id=event.get("payload", {}).get("skill_id"),
                                )
                                asyncio.create_task(runner._sync_config())
                            elif event["type"] == "skill:updated":
                                logger.info(
                                    "runner.skill_updated_event_detected",
                                    agent_id=runner.config.id,
                                    skill_id=event.get("payload", {}).get("skill_id"),
                                )
                                runner._pending_tool_reload = True
                            elif event["type"] == "session:message":
                                payload = event["payload"]
                                logger.info(
                                    "runner.session_message_detected",
                                    session_id=payload.get("session_id"),
                                )
                                # Cache token_map for local re-hydration
                                token_map = payload.get("token_map", {})
                                if token_map:
                                    session_id = payload.get("session_id")
                                    runner._pii_client.cache_token_map(session_id, token_map)
                                    logger.info("runner.token_map_cached", session_id=session_id, tokens=len(token_map))
                                # Store per-session metadata for streaming mode override
                                runner._current_session_metadata = payload.get("metadata") or {}
                                asyncio.create_task(runner._execute_session_message(payload))
                    finally:
                        drain_task.cancel()
                        runner._websocket = None
            except Exception as e:
                if runner._running:
                    error_str = str(e).lower()
                    if "401" in error_str or "403" in error_str or "policy violation" in error_str:
                        try:
                            await runner.client.recover_token(runner.config.id)
                            logger.info("runner.ws_token_recovered", agent_id=runner.config.id)
                        except Exception as rec_err:
                            logger.error(
                                "runner.ws_token_recovery_failed",
                                agent_id=runner.config.id,
                                error=str(rec_err),
                            )
                    logger.error("runner.ws_error", error=str(e), next_retry=retry_delay)
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_delay)

    async def notify_session_ready(self, session_id: str):
        """Explicitly mark session as ready so UI clears streaming state.

        Covers edge cases where reply_to_session is not reached (crashes, timeouts).
        """
        try:
            await self.runner.client.update_session_status(session_id, "ready")
            logger.info("runner.session_status_reset", session_id=session_id, status="ready")
        except Exception as e:
            logger.warning("runner.session_status_reset_failed", session_id=session_id, error=str(e))
