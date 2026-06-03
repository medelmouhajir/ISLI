"""Browser session management — persistent Playwright contexts per agent."""

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import Any

import structlog
from playwright.async_api import BrowserContext, Page, Playwright

from .exceptions import BrowserSessionError

logger = structlog.get_logger()


def _get_redis_client(redis_url: str):
    """Lazy import redis to avoid import-time side effects."""
    from redis.asyncio import Redis

    return Redis.from_url(redis_url, decode_responses=True)


@dataclass
class BrowserSession:
    """In-memory representation of a single agent's browser session."""

    context: BrowserContext
    page: Page
    ref_map: dict[str, Any] = field(default_factory=dict)
    last_accessed: float = field(default_factory=time.time)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    console_logs: list[dict[str, Any]] = field(default_factory=list)
    console_cursor: int = 0

    def clear_refs(self) -> None:
        """Invalidate all ref IDs — call before navigation to prevent stale clicks."""
        self.ref_map.clear()

    def append_console_log(self, msg: dict[str, Any]) -> None:
        """Append a console log entry."""
        self.console_logs.append(msg)

    def get_console_logs(self, since_cursor: int = 0) -> tuple[list[dict[str, Any]], int]:
        """Return logs since the given cursor and the new cursor position."""
        logs = self.console_logs[since_cursor:]
        next_cursor = len(self.console_logs)
        return logs, next_cursor

    def reset_console(self) -> None:
        """Clear all console logs and reset cursor — call on navigate."""
        self.console_logs.clear()
        self.console_cursor = 0


class BrowserSessionManager:
    """Manages persistent BrowserContext instances keyed by agent_id.

    Playwright objects (BrowserContext, Page, ElementHandle) cannot be
    serialized, so sessions live in an in-memory dict. Redis is used only
    for TTL heartbeats and cross-instance awareness.
    """

    def __init__(
        self,
        redis_url: str,
        playwright: Playwright,
        session_dir: str,
        ttl_seconds: int = 600,
        max_concurrent: int = 5,
    ):
        self.redis = _get_redis_client(redis_url)
        self.playwright = playwright
        self.session_dir = session_dir
        self.ttl_seconds = ttl_seconds
        self.max_concurrent = max_concurrent
        self._sessions: dict[str, BrowserSession] = {}
        self._cleanup_task: asyncio.Task | None = None
        self._shutdown_event = asyncio.Event()

    async def start_cleanup_loop(self) -> None:
        """Start the background cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("browser.cleanup_loop_started", interval_s=60)

    async def stop_cleanup_loop(self) -> None:
        """Signal and wait for the cleanup task to finish."""
        self._shutdown_event.set()
        if self._cleanup_task and not self._cleanup_task.done():
            try:
                await asyncio.wait_for(self._cleanup_task, timeout=5)
            except TimeoutError:
                self._cleanup_task.cancel()

    async def _cleanup_loop(self) -> None:
        """Background task that closes stale sessions every 60 seconds."""
        while not self._shutdown_event.is_set():
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(), timeout=60
                )
            except TimeoutError:
                await self._close_stale_sessions()

    async def _close_stale_sessions(self) -> None:
        """Close sessions whose last access exceeded TTL."""
        now = time.time()
        stale: list[str] = []
        for agent_id, session in self._sessions.items():
            if now - session.last_accessed > self.ttl_seconds:
                stale.append(agent_id)

        for agent_id in stale:
            logger.info("browser.session_stale", agent_id=agent_id)
            await self.close_session(agent_id)

    async def get_or_create(self, agent_id: str) -> BrowserSession:
        """Get an existing session or create a new one.

        Raises:
            BrowserSessionError: If the max concurrent session limit is reached.
        """
        # Fast path: existing session
        if agent_id in self._sessions:
            session = self._sessions[agent_id]
            session.last_accessed = time.time()
            return session

        # Guard: max concurrent sessions
        if len(self._sessions) >= self.max_concurrent:
            logger.warning(
                "browser.max_concurrent_reached",
                current=len(self._sessions),
                max=self.max_concurrent,
            )
            raise BrowserSessionError(
                f"Browser session pool exhausted. Max concurrent: {self.max_concurrent}. "
                "Retry after 30 seconds."
            )

        # Create persistent user data dir for cookies / localStorage
        user_data_dir = os.path.join(self.session_dir, agent_id)
        os.makedirs(user_data_dir, exist_ok=True)

        try:
            context = await self.playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=True,
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/119.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()
        except Exception as exc:
            logger.error("browser.context_launch_failed", agent_id=agent_id, error=str(exc))
            raise BrowserSessionError(f"Failed to launch browser context: {exc}") from exc

        session = BrowserSession(context=context, page=page)
        self._sessions[agent_id] = session

        # Attach console listener
        page.on("console", lambda msg: session.append_console_log({
            "type": msg.type,
            "text": msg.text,
            "location": str(msg.location) if msg.location else None,
            "time": time.time(),
        }))

        # Refresh Redis TTL
        await self.touch(agent_id)

        logger.info(
            "browser.session_created",
            agent_id=agent_id,
            total_sessions=len(self._sessions),
        )
        return session

    async def close_session(self, agent_id: str) -> None:
        """Close a session and clean up resources."""
        session = self._sessions.pop(agent_id, None)
        if not session:
            return

        try:
            await session.context.close()
        except Exception as exc:
            logger.warning("browser.context_close_error", agent_id=agent_id, error=str(exc))

        try:
            await self.redis.delete(f"browser:session:{agent_id}")
        except Exception as exc:
            logger.warning("browser.redis_delete_error", agent_id=agent_id, error=str(exc))

        logger.info("browser.session_closed", agent_id=agent_id)

    async def touch(self, agent_id: str) -> None:
        """Refresh the Redis TTL heartbeat for a session."""
        try:
            await self.redis.setex(
                f"browser:session:{agent_id}",
                self.ttl_seconds,
                "active",
            )
        except Exception as exc:
            logger.warning("browser.redis_touch_error", agent_id=agent_id, error=str(exc))

    async def close_all(self) -> None:
        """Close all sessions — call during shutdown."""
        agent_ids = list(self._sessions.keys())
        for agent_id in agent_ids:
            await self.close_session(agent_id)
