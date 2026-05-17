import os
from contextlib import asynccontextmanager
from typing import Any
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
import structlog

from .telemetry import instrument_fastapi, get_trace_id
from .config import get_settings
from .auth import require_internal_auth


SERVICE_NAME = "isli-skills"
WORKSPACE_URL = os.getenv("WORKSPACE_URL", "http://localhost:8300")

logger = structlog.get_logger()

SKILL_REGISTRY: dict[str, dict[str, Any]] = {}


class RegisterSkill(BaseModel):
    name: str
    endpoint: str | None = None
    workspace_path: str | None = None
    agent_id: str | None = None
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
async def list_skills(_auth: dict = Depends(require_internal_auth)):
    return {"skills": list(SKILL_REGISTRY.values())}


@app.post("/skills", status_code=201)
async def register_skill(skill: RegisterSkill, _auth: dict = Depends(require_internal_auth)):
    if skill.name in SKILL_REGISTRY:
        raise HTTPException(status_code=409, detail=f"Skill '{skill.name}' already registered")
    SKILL_REGISTRY[skill.name] = skill.model_dump()
    logger.info("skills.registered", name=skill.name, endpoint=skill.endpoint)
    return {"status": "registered", "skill": skill.model_dump()}


@app.get("/skills/{name}/health")
async def skill_health(name: str, _auth: dict = Depends(require_internal_auth)):
    skill = SKILL_REGISTRY.get(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return {"status": "ok", "skill": name, "endpoint": skill.get("endpoint")}


@app.post("/browse")
async def browse(request: BrowseRequest, _auth: dict = Depends(require_internal_auth)):
    """Browser automation endpoint."""
    logger.info("skills.browse", url=request.url)
    result = await browse_url(
        url=request.url,
        wait_for_selector=request.wait_for_selector,
        screenshot=request.screenshot
    )
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@app.post("/skills/{name}/invoke")
async def invoke_skill(name: str, body: InvokeSkill, _auth: dict = Depends(require_internal_auth)):
    skill = SKILL_REGISTRY.get(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

    # CASE 1: Standard microservice skill
    if skill.get("endpoint"):
        # In production, this proxies to the skill's actual endpoint
        logger.info("skills.invoked.proxy", name=name, action=body.action)
        return {
            "status": "ok",
            "skill": name,
            "action": body.action,
            "result": {"note": "Skill invocation proxied", "payload_received": body.payload},
        }

    # CASE 2: Dynamic Skill (In-Memory execution from workspace)
    if skill.get("workspace_path") and skill.get("agent_id"):
        logger.info("skills.invoked.dynamic", name=name, action=body.action, agent_id=skill["agent_id"])
        
        # 1. Fetch code from workspace
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{WORKSPACE_URL}/read",
                    json={"agent_id": skill["agent_id"], "path": skill["workspace_path"]}
                )
                resp.raise_for_status()
                code = resp.json().get("content")
        except Exception as exc:
            logger.error("skills.dynamic.fetch_failed", name=name, error=str(exc))
            raise HTTPException(status_code=502, detail=f"Failed to fetch dynamic skill code: {exc}")

        # 2. Execute code in-memory with restricted builtins
        try:
            # Provide a safe subset of builtins + LLM capability
            import httpx

            async def ask_llm(prompt: str, model: str = "qwen2.5:7b") -> str:
                """Utility for smart skills to call the local Keeper model."""
                KEEPER_URL = os.getenv("KEEPER_URL", "http://keeper:8001")
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        f"{KEEPER_URL}/generate",
                        json={"prompt": prompt, "model": model}
                    )
                    resp.raise_for_status()
                    return resp.json().get("text", "")

            safe_builtins = {
                'print': print, 'range': range, 'len': len, 'int': int, 'float': float,
                'str': str, 'list': list, 'dict': dict, 'tuple': tuple, 'set': set,
                'bool': bool, 'min': min, 'max': max, 'sum': sum, 'any': any, 'all': all,
                'sorted': sorted, 'abs': abs, 'round': round, 'enumerate': enumerate,
                'zip': zip, 'Exception': Exception, 'ValueError': ValueError, 
                'TypeError': TypeError, 'AttributeError': AttributeError, 'KeyError': KeyError,
                'RuntimeError': RuntimeError, 'StopIteration': StopIteration,
            }

            namespace: dict[str, Any] = {
                "__builtins__": safe_builtins,
                "ask_llm": ask_llm,
                "httpx": httpx,
            }

            exec(code, namespace)
            
            # Require an 'async def run(payload: dict) -> dict:' function
            if "run" not in namespace:
                raise AttributeError("Dynamic skill must define a 'run' function")
                
            run_func = namespace["run"]
            import asyncio
            if asyncio.iscoroutinefunction(run_func):
                result = await run_func(body.payload)
            else:
                result = run_func(body.payload)
                
            return {
                "status": "ok",
                "skill": name,
                "action": body.action,
                "result": result
            }
        except Exception as exc:
            logger.error("skills.dynamic.execution_failed", name=name, error=str(exc))
            raise HTTPException(status_code=500, detail=f"Dynamic skill execution error: {exc}")

    raise HTTPException(status_code=400, detail=f"Skill '{name}' is improperly configured")
