from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from isli_core.config import get_settings
from isli_core.routers import (
    agents,
    audio,
    backups,
    blobs,
    channels,
    commands,
    internal,
    memory,
    model_management,
    notifications,
    prompts,
    rooms,
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
from isli_core.routers.health import health_router, legacy_health_router
from isli_core.startup import lifespan
from isli_core.telemetry import instrument_fastapi

SERVICE_NAME = "isli-core"

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
v1.include_router(blobs.router)
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
v1.include_router(rooms.router)
v1.include_router(health_router)

app.include_router(v1)
app.include_router(legacy_health_router)
