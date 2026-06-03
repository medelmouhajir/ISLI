import asyncio
import os
import signal
import structlog
from contextlib import asynccontextmanager
from importlib.metadata import version, PackageNotFoundError

from fastapi import FastAPI, APIRouter, Response
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import init_db, close_db
from .redis_client import get_redis
from .startup_validation import validate_startup_secrets
from .telemetry import instrument_fastapi, get_trace_id
from .routers import (
    agents,
    audio,
    backups,
    channels,
    commands,
    internal,
    memory,
    model_management,
    notifications,
    prompts,
    secrets,
    security,
    sessions,
    settings,
    shared_workspaces,
    skills,
    stt,
    system,
    tasks,
    transparency,
    workspaces,
    ws,
)

SERVICE_NAME = "isli-core"

logger = structlog.get_logger()


def _app_version() -> str:
    try:
        return version("isli-core")
    except PackageNotFoundError:
        return "0.0.0"


def _git_sha() -> str:
    return os.getenv("GIT_SHA", "unknown")


def _handle_sigterm():
    logger.info("core.sigterm_received", service=SERVICE_NAME)
    _shutdown_event.set()


_shutdown_event = asyncio.Event()


async def _recovery_loop() -> None:
    """Background loop for checkpoint recovery worker."""
    import asyncio
    from isli_core.db import async_session
    from isli_core.jobs.checkpoint_recovery import CheckpointRecoveryWorker

    while True:
        await asyncio.sleep(300)  # Run every 5 minutes
        if async_session is None:
            continue
        try:
            async with async_session() as session:
                await CheckpointRecoveryWorker.run_once(session)
                await session.commit()
        except Exception as exc:
            import structlog
            structlog.get_logger().error("recovery_loop.error", error=str(exc))


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_startup_secrets()
    settings = get_settings()
    await init_db(settings.database_url)
    loop = asyncio.get_running_loop()
    try:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, _handle_sigterm)
    except NotImplementedError:
        # Windows does not support add_signal_handler in ProactorEventLoop
        pass
    logger.info("core.startup", service=SERVICE_NAME)

    # Start background workers
    from isli_core.jobs.session_cron import SessionCronJob
    from isli_core.jobs.scheduler_worker import SchedulerWorker
    from isli_core.jobs.checkpoint_recovery import CheckpointRecoveryWorker
    from isli_core.jobs.context_injector import ContextInjectorWorker
    from isli_core.jobs.journal_worker import JournalWorker
    from isli_core.jobs.session_context_injector import SessionContextInjectorWorker
    from isli_core.jobs.memory_worker import MemoryWorker
    from isli_core.jobs.outbox_worker import OutboxWorker
    from isli_core.jobs.memory_gc_worker import MemoryGCWorker
    from isli_core.jobs.chromadb_backup_worker import ChromaBackupWorker
    from isli_core.routers.ws import redis_listener
    from isli_core.jobs.heartbeat_validator import heartbeat_validator_worker
    from isli_core.jobs.budget_alerter import BudgetAlertWorker
    from isli_core.jobs.attachment_cleanup import AttachmentCleanupWorker
    from isli_core.jobs.audio_cleanup import AudioCleanupWorker
    from isli_core.notification.digest import DigestWorker
    from isli_core.services.process_manager import AgentProcessManager

    # Register notification outbox handlers
    from isli_core.jobs.outbox_worker import register_outbox_handler
    from isli_core.notification.delivery import deliver_in_app
    from isli_core.notification.delivery_external import deliver_external
    from isli_core.notification.delivery_webpush import deliver_web_push
    register_outbox_handler("notification:in_app", deliver_in_app)
    register_outbox_handler("notification:external", deliver_external)
    register_outbox_handler("notification:web_push", deliver_web_push)
    logger.info("startup.notification_handlers_registered")

    # Initialize AgentProcessManager
    sdk_path = os.getenv("AGENT_SDK_PATH", "../isli-agent-sdk")
    app.state.process_manager = AgentProcessManager(
        sdk_path=sdk_path,
        core_url=settings.core_api_url
    )

    # Reset stuck "starting" agents to "stopped"
    from isli_core.models import Agent
    from sqlalchemy import update, select
    from isli_core.db import get_db_session_manual
    async with get_db_session_manual() as session:
        result = await session.execute(
            update(Agent)
            .where(Agent.status == "starting", Agent.deleted_at.is_(None))
            .values(status="stopped")
            .returning(Agent.id)
        )
        reset_ids = [row[0] for row in result.all()]
        await session.commit()
        if reset_ids:
            logger.info("startup.reset_stuck_starting_agents", agent_ids=reset_ids)

    # Reconcile with any Docker containers that survived a Core restart
    await app.state.process_manager.reconcile()

    # Restart any agents that were online before Core went down
    async with get_db_session_manual() as session:
        result = await session.execute(
            select(Agent).where(Agent.status == "online", Agent.deleted_at.is_(None))
        )
        online_agents = result.scalars().all()
        for agent in online_agents:
            if not app.state.process_manager.is_running(agent.id):
                logger.info("core.startup.restart_agent", agent_id=agent.id)
                try:
                    await app.state.process_manager.spawn(agent.id)
                except Exception as exc:
                    logger.error("core.startup.restart_failed", agent_id=agent.id, error=str(exc))

    cron_task = asyncio.create_task(SessionCronJob.loop())
    scheduler_task = asyncio.create_task(SchedulerWorker.loop())
    recovery_task = asyncio.create_task(_recovery_loop())
    context_task = asyncio.create_task(ContextInjectorWorker.loop())
    session_ctx_task = asyncio.create_task(SessionContextInjectorWorker.loop())
    journal_task = asyncio.create_task(JournalWorker.loop())
    memory_task = asyncio.create_task(MemoryWorker.loop())
    memory_gc_task = asyncio.create_task(MemoryGCWorker.loop())
    outbox_task = asyncio.create_task(OutboxWorker.loop())
    digest_task = asyncio.create_task(DigestWorker.loop())
    ws_task = asyncio.create_task(redis_listener())
    heartbeat_task = asyncio.create_task(heartbeat_validator_worker())
    budget_alert_task = asyncio.create_task(BudgetAlertWorker.loop())
    attachment_cleanup_task = asyncio.create_task(AttachmentCleanupWorker.loop())
    audio_cleanup_task = asyncio.create_task(AudioCleanupWorker.loop())
    chroma_backup_task = asyncio.create_task(ChromaBackupWorker.loop())

    yield

    logger.info("core.shutdown.drain", service=SERVICE_NAME)
    cron_task.cancel()
    scheduler_task.cancel()
    recovery_task.cancel()
    context_task.cancel()
    session_ctx_task.cancel()
    journal_task.cancel()
    memory_task.cancel()
    memory_gc_task.cancel()
    outbox_task.cancel()
    digest_task.cancel()
    ws_task.cancel()
    heartbeat_task.cancel()
    budget_alert_task.cancel()
    attachment_cleanup_task.cancel()
    audio_cleanup_task.cancel()
    chroma_backup_task.cancel()
    try:
        await cron_task
    except asyncio.CancelledError:
        pass
    try:
        await recovery_task
    except asyncio.CancelledError:
        pass
    try:
        await session_ctx_task
    except asyncio.CancelledError:
        pass
    try:
        await memory_gc_task
    except asyncio.CancelledError:
        pass
    try:
        await audio_cleanup_task
    except asyncio.CancelledError:
        pass
    try:
        await chroma_backup_task
    except asyncio.CancelledError:
        pass

    await asyncio.wait_for(_shutdown_event.wait(), timeout=30.0)
    await close_db()
    logger.info("core.shutdown", service=SERVICE_NAME)


app = FastAPI(
    title="ISLI Core API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)
instrument_fastapi(app, SERVICE_NAME)

cors_origins = [o.strip() for o in (get_settings().cors_origins or "").split(",") if o.strip()]
if not cors_origins:
    cors_origins = ["http://localhost:5173", "http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# v1 API router
v1 = APIRouter(prefix="/v1")

v1.include_router(agents.router)
v1.include_router(audio.router)
v1.include_router(tasks.router)
v1.include_router(skills.router)
v1.include_router(workspaces.router)
v1.include_router(shared_workspaces.router)
v1.include_router(memory.router)
v1.include_router(channels.router)
v1.include_router(sessions.router)
v1.include_router(commands.router)
v1.include_router(system.router)
v1.include_router(transparency.router)
v1.include_router(security.router)
v1.include_router(ws.router)
v1.include_router(settings.router)
v1.include_router(model_management.router)
v1.include_router(internal.router)
v1.include_router(stt.router)
v1.include_router(backups.router)
v1.include_router(secrets.router)
v1.include_router(prompts.router)
v1.include_router(notifications.router)


@v1.get("/metrics")
async def metrics_v1():
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@v1.get("/health")
async def health_v1():
    trace_id = get_trace_id()
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": _app_version(),
        "git_sha": _git_sha(),
        "trace_id": trace_id,
    }


@v1.get("/ready")
async def ready_v1():
    db_ok = False
    redis_ok = False
    try:
        from sqlalchemy import text
        from .db import engine
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            db_ok = True
    except Exception as exc:
        logger.warning("core.ready.db_failed", error=str(exc))

    try:
        redis = await get_redis()
        await redis.ping()
        redis_ok = True
    except Exception as exc:
        logger.warning("core.ready.redis_failed", error=str(exc))

    if db_ok and redis_ok:
        return {
            "status": "ready",
            "service": SERVICE_NAME,
            "version": _app_version(),
            "git_sha": _git_sha(),
            "database": "ok",
            "redis": "ok",
        }
    return {
        "status": "not_ready",
        "service": SERVICE_NAME,
        "version": _app_version(),
        "git_sha": _git_sha(),
        "database": "ok" if db_ok else "fail",
        "redis": "ok" if redis_ok else "fail",
    }


@v1.get("/live")
async def live_v1():
    return {"status": "alive", "service": SERVICE_NAME, "version": _app_version()}


app.include_router(v1)

# Legacy unversioned endpoints
@app.get("/metrics")
async def metrics():
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
async def health():
    trace_id = get_trace_id()
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": _app_version(),
        "git_sha": _git_sha(),
        "trace_id": trace_id,
    }


@app.get("/ready")
async def ready():
    db_ok = False
    redis_ok = False
    try:
        from sqlalchemy import text
        from .db import engine
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            db_ok = True
    except Exception as exc:
        logger.warning("core.ready.db_failed", error=str(exc))

    try:
        redis = await get_redis()
        await redis.ping()
        redis_ok = True
    except Exception as exc:
        logger.warning("core.ready.redis_failed", error=str(exc))

    if db_ok and redis_ok:
        return {
            "status": "ready",
            "service": SERVICE_NAME,
            "database": "ok",
            "redis": "ok",
        }
    return {
        "status": "not_ready",
        "service": SERVICE_NAME,
        "database": "ok" if db_ok else "fail",
        "redis": "ok" if redis_ok else "fail",
    }


@app.get("/live")
async def live():
    return {"status": "alive", "service": SERVICE_NAME}
