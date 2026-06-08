"""Unified startup lifespan for isli-core.

Moves all startup logic out of ``main.py`` into focused submodules.
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from isli_core.config import get_settings
from isli_core.db import close_db, init_db
from isli_core.startup_validation import validate_startup_secrets

from .agents import initialize_process_manager
from .infra import setup_signals, wait_for_shutdown
from .notifications import register_notification_handlers
from .outbox import register_handlers as register_outbox_handlers
from .workers import WorkerManager
from .settings_seed import seed_default_settings
from isli_core.redis_streams import ensure_stream_group
from isli_core.redis_client import get_redis
from isli_core.estop import EStopManager

logger = structlog.get_logger()

STREAM_NAME = "context:requests"
GROUP_NAME = "context_workers"


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_startup_secrets()
    settings = get_settings()
    await init_db(settings.database_url)
    await seed_default_settings()
    await setup_signals()
    logger.info("core.startup", service="isli-core")

    # Initialize E-Stop
    redis = await get_redis(settings.redis_url)
    estop = EStopManager(redis)
    await estop.start()
    app.state.estop = estop

    register_notification_handlers()
    register_outbox_handlers()
    await initialize_process_manager(app)

    # Ensure Redis Stream consumer group exists before any worker starts.
    # This prevents messages written by routers during startup from being
    # unprocessable until the worker loop initialises the group.
    await ensure_stream_group(STREAM_NAME, GROUP_NAME)

    manager = WorkerManager()
    await manager.start_all()

    yield

    logger.info("core.shutdown.drain", service="isli-core")
    await estop.stop()
    await manager.stop_all()
    await wait_for_shutdown()
    await close_db()
    logger.info("core.shutdown", service="isli-core")
