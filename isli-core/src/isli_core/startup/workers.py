"""Background worker lifecycle: start all on boot, cancel cleanly on shutdown."""

import asyncio
import importlib

import structlog

logger = structlog.get_logger()

_WORKER_SPECS = [
    "isli_core.jobs.session_cron:SessionCronJob.loop",
    "isli_core.jobs.scheduler_worker:SchedulerWorker.loop",
    "isli_core.jobs.checkpoint_recovery:CheckpointRecoveryWorker.loop",
    "isli_core.jobs.context_worker:ContextWorker.loop",
    "isli_core.jobs.journal_worker:JournalWorker.loop",
    "isli_core.jobs.memory_worker:MemoryWorker.loop",
    "isli_core.jobs.memory_gc_worker:MemoryGCWorker.loop",
    "isli_core.jobs.outbox_worker:OutboxWorker.loop",
    "isli_core.notification.digest:DigestWorker.loop",
    "isli_core.routers.ws:redis_listener",
    "isli_core.jobs.heartbeat_validator:heartbeat_validator_worker",
    "isli_core.jobs.budget_alerter:BudgetAlertWorker.loop",
    "isli_core.jobs.attachment_cleanup:AttachmentCleanupWorker.loop",
    "isli_core.jobs.audio_cleanup:AudioCleanupWorker.loop",
    "isli_core.jobs.chromadb_backup_worker:ChromaBackupWorker.loop",
    "isli_core.jobs.skill_update_worker:SkillUpdateWorker.loop",
]


def _resolve_coro(spec: str):
    """Resolve a ``module.path:factory.attr`` string into a running coroutine."""
    module_path, attr_path = spec.split(":", 1)
    module = importlib.import_module(module_path)
    obj = module
    for attr in attr_path.split("."):
        obj = getattr(obj, attr)
    return obj()


class WorkerManager:
    """Encapsulates creation and cancellation of all background workers."""

    def __init__(self):
        self.tasks: dict[str, asyncio.Task] = {}

    async def start_all(self):
        for spec in _WORKER_SPECS:
            name = spec.split(":")[-1].split(".")[-1]
            try:
                coro = _resolve_coro(spec)
                self.tasks[name] = asyncio.create_task(coro, name=f"worker-{name}")
            except Exception as exc:
                logger.error("startup.worker_failed_to_start", worker=name, error=str(exc))
                raise
        logger.info("startup.workers_started", count=len(self.tasks))

    async def stop_all(self):
        for name, task in self.tasks.items():
            task.cancel()
            logger.debug("shutdown.worker_cancelled", worker=name)

        results = await asyncio.gather(*self.tasks.values(), return_exceptions=True)

        for name, result in zip(self.tasks.keys(), results, strict=False):
            if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                logger.warning("shutdown.worker_error", worker=name, error=str(result))

        logger.info("shutdown.workers_stopped", count=len(self.tasks))
