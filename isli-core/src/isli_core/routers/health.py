"""Health, readiness, liveness, and metrics endpoints."""

import os
from importlib.metadata import PackageNotFoundError, version

import structlog
from fastapi import APIRouter, Response
from sqlalchemy import text

import isli_core.db as db_module
from isli_core.redis_client import get_redis
from isli_core.telemetry import get_trace_id

logger = structlog.get_logger()

SERVICE_NAME = "isli-core"


def _app_version() -> str:
    try:
        return version("isli-core")
    except PackageNotFoundError:
        return "0.0.0"


def _git_sha() -> str:
    return os.getenv("GIT_SHA", "unknown")


# ── v1 router (mounted under /v1) ──────────────────────────────────────────
health_router = APIRouter(tags=["health"])


@health_router.get("/metrics")
async def metrics_v1():
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@health_router.get("/health")
async def health_v1():
    trace_id = get_trace_id()
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": _app_version(),
        "git_sha": _git_sha(),
        "trace_id": trace_id,
    }


@health_router.get("/ready")
async def ready_v1():
    db_ok = False
    redis_ok = False
    try:
        async with db_module.engine.connect() as conn:
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


@health_router.get("/live")
async def live_v1():
    return {"status": "alive", "service": SERVICE_NAME, "version": _app_version()}


# ── Legacy router (mounted at root) ────────────────────────────────────────
legacy_health_router = APIRouter(tags=["health"])


@legacy_health_router.get("/metrics")
async def metrics_legacy():
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@legacy_health_router.get("/health")
async def health_legacy():
    trace_id = get_trace_id()
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": _app_version(),
        "git_sha": _git_sha(),
        "trace_id": trace_id,
    }


@legacy_health_router.get("/ready")
async def ready_legacy():
    db_ok = False
    redis_ok = False
    try:
        async with db_module.engine.connect() as conn:
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


@legacy_health_router.get("/live")
async def live_legacy():
    return {"status": "alive", "service": SERVICE_NAME}
