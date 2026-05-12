import os
import structlog
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .telemetry import instrument_fastapi, get_trace_id
from .config import get_settings

SERVICE_NAME = "isli-skills"

logger = structlog.get_logger()

SKILL_REGISTRY: dict[str, dict[str, Any]] = {}


class RegisterSkill(BaseModel):
    name: str
    endpoint: str
    health_endpoint: str | None = None
    description: str | None = None


class InvokeSkill(BaseModel):
    action: str
    payload: dict[str, Any]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("skills.startup", service=SERVICE_NAME)
    yield
    logger.info("skills.shutdown", service=SERVICE_NAME)


app = FastAPI(
    title="ISLI Skills",
    version="0.1.0",
    lifespan=lifespan,
)
instrument_fastapi(app, SERVICE_NAME)


@app.get("/health")
async def health():
    trace_id = get_trace_id()
    return {"status": "ok", "service": SERVICE_NAME, "trace_id": trace_id}


@app.get("/ready")
async def ready():
    return {"status": "ready", "service": SERVICE_NAME, "skills_registered": len(SKILL_REGISTRY)}


@app.get("/live")
async def live():
    return {"status": "alive", "service": SERVICE_NAME}


@app.get("/skills")
async def list_skills():
    return {"skills": list(SKILL_REGISTRY.values())}


@app.post("/skills", status_code=201)
async def register_skill(skill: RegisterSkill):
    if skill.name in SKILL_REGISTRY:
        raise HTTPException(status_code=409, detail=f"Skill '{skill.name}' already registered")
    SKILL_REGISTRY[skill.name] = skill.model_dump()
    logger.info("skills.registered", name=skill.name, endpoint=skill.endpoint)
    return {"status": "registered", "skill": skill.model_dump()}


@app.get("/skills/{name}/health")
async def skill_health(name: str):
    skill = SKILL_REGISTRY.get(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return {"status": "ok", "skill": name, "endpoint": skill.get("endpoint")}


@app.post("/skills/{name}/invoke")
async def invoke_skill(name: str, body: InvokeSkill):
    skill = SKILL_REGISTRY.get(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    # In production, this proxies to the skill's actual endpoint
    logger.info("skills.invoked", name=name, action=body.action)
    return {
        "status": "ok",
        "skill": name,
        "action": body.action,
        "result": {"note": "Skill invocation proxied", "payload_received": body.payload},
    }
