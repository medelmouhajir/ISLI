"""Infrastructure lifecycle helpers: signals, shutdown coordination."""

import asyncio
import contextlib
import signal

import structlog

logger = structlog.get_logger()

_shutdown_event = asyncio.Event()


def handle_sigterm():
    logger.info("core.sigterm_received")
    _shutdown_event.set()


async def setup_signals():
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            # Windows does not support add_signal_handler in ProactorEventLoop
            loop.add_signal_handler(sig, handle_sigterm)


async def wait_for_shutdown(timeout: float = 30.0):
    await asyncio.wait_for(_shutdown_event.wait(), timeout=timeout)
