import os
import ast
import json
from contextlib import asynccontextmanager
from typing import Any
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
import structlog
from datetime import datetime, timezone

from .telemetry import instrument_fastapi, get_trace_id
from .config import get_settings
from .auth import require_internal_auth, create_internal_token
from .playwright_service import browse_url
from .debugger import execute_with_trace
from .db_query import validate_query, execute_query
from .browser.router import router as browser_router, set_session_manager
from .browser.session_manager import BrowserSessionManager


SERVICE_NAME = "isli-skills"
WORKSPACE_URL = os.getenv("WORKSPACE_URL", "http://localhost:8300")
REGISTRY_FILE = os.getenv("REGISTRY_FILE", "/tmp/skill_registry.json")

logger = structlog.get_logger()

SKILL_REGISTRY: dict[str, dict[str, Any]] = {}


def load_registry():
    global SKILL_REGISTRY
    if os.path.exists(REGISTRY_FILE):
        try:
            with open(REGISTRY_FILE, "r") as f:
                SKILL_REGISTRY = json.load(f)
            logger.info("skills.registry_loaded", count=len(SKILL_REGISTRY))
        except Exception as e:
            logger.error("skills.registry_load_failed", error=str(e))


def save_registry():
    try:
        with open(REGISTRY_FILE, "w") as f:
            json.dump(SKILL_REGISTRY, f, indent=2)
    except Exception as e:
        logger.error("skills.registry_save_failed", error=str(e))


def validate_skill_code(code: str) -> None:
    """Perform AST analysis on dynamic skill code for security and compliance."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise HTTPException(status_code=400, detail=f"Syntax error in skill code: {e}")

    # 1. Check for mandatory 'async def run(payload: dict)'
    found_run = False
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "run":
            found_run = True
            # Basic check for one argument
            if len(node.args.args) != 1:
                raise HTTPException(status_code=400, detail="Skill 'run' function must accept exactly one argument: 'payload'")
            break
    
    if not found_run:
        raise HTTPException(status_code=400, detail="Dynamic skill must define an 'async def run(payload: dict)' function")

    # 2. Check for forbidden imports or patterns
    # We already restrict builtins at runtime, but AST check adds defense-in-depth
    FORBIDDEN_MODULES = {"os", "sys", "subprocess", "socket", "pickle", "marshal"}
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split('.')[0] in FORBIDDEN_MODULES:
                    raise HTTPException(status_code=400, detail=f"Import of module '{alias.name}' is forbidden")
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split('.')[0] in FORBIDDEN_MODULES:
                raise HTTPException(status_code=400, detail=f"Import from module '{node.module}' is forbidden")
        
        # Prevent recursion (optional/heuristic)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "run":
            # Simple check for self-call named 'run'
            raise HTTPException(status_code=400, detail="Recursive calls to 'run' are forbidden")

    # 3. Complexity limits
    if len(tree.body) > 500:
        raise HTTPException(status_code=400, detail="Skill code exceeds maximum complexity (500 lines)")


class RegisterSkill(BaseModel):
    name: str
    endpoint: str | None = None
    workspace_path: str | None = None
    agent_id: str | None = None
    health_endpoint: str | None = None
    description: str | None = None
    category: str | None = None
    usage_count: int = 0
    last_used_at: str | None = None
    created_at: str | None = None


class UpdateSkillRequest(BaseModel):
    name: str
    endpoint: str | None = None
    workspace_path: str | None = None
    agent_id: str | None = None
    health_endpoint: str | None = None
    description: str | None = None
    category: str | None = None


class TestSkillRequest(BaseModel):
    code: str
    payload: dict[str, Any]


class DebugRequest(BaseModel):
    code: str
    payload: dict[str, Any] = {}
    breakpoints: list[int] = []
    mode: str = "breakpoints"
    max_steps: int = 1000
    max_trace_size: int = 32768
    only_changes: bool = True
    include_locals: bool = True
    include_globals: bool = False
    watch_expressions: list[str] = []
    stdin: str = ""


class InvokeSkill(BaseModel):
    action: str
    payload: dict[str, Any]


class BrowseRequest(BaseModel):
    url: str
    wait_for_selector: str | None = None
    screenshot: bool = False


class FetchRequest(BaseModel):
    url: str
    agent_id: str | None = None


class SearchRequest(BaseModel):
    query: str
    max_results: int = 5


class SummarizeRequest(BaseModel):
    text: str
    max_length: int = 256


class EmbedRequest(BaseModel):
    input: str
    model: str | None = None


class DbQueryRequest(BaseModel):
    query: str
    agent_id: str | None = None
    schema_name: str | None = None
    max_rows: int = 100


KEEPER_URL = os.getenv("KEEPER_URL", "http://localhost:8001")
SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8080/search")


_playwright: Any | None = None
_session_manager: BrowserSessionManager | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _playwright, _session_manager
    logger.info("skills.startup", service=SERVICE_NAME)
    load_registry()

    # Initialize browser automation
    settings = get_settings()
    try:
        from playwright.async_api import async_playwright

        _playwright = await async_playwright().start()
        redis_url = settings.browser_redis_url or settings.redis_url or "redis://localhost:6379"
        _session_manager = BrowserSessionManager(
            redis_url=redis_url,
            playwright=_playwright,
            session_dir=settings.browser_session_dir,
            ttl_seconds=settings.browser_session_ttl,
            max_concurrent=settings.browser_max_concurrent_sessions,
        )
        await _session_manager.start_cleanup_loop()
        set_session_manager(_session_manager)
        logger.info(
            "browser.initialized",
            session_dir=settings.browser_session_dir,
            ttl=settings.browser_session_ttl,
            max_concurrent=settings.browser_max_concurrent_sessions,
        )
    except Exception as exc:
        logger.error("browser.init_failed", error=str(exc))
        # Non-fatal: the rest of the skills service still works

    yield

    # Shutdown browser automation
    if _session_manager:
        try:
            await _session_manager.stop_cleanup_loop()
            await _session_manager.close_all()
        except Exception as exc:
            logger.error("browser.shutdown_error", error=str(exc))
    if _playwright:
        try:
            await _playwright.stop()
        except Exception as exc:
            logger.error("browser.playwright_stop_error", error=str(exc))

    logger.info("skills.shutdown", service=SERVICE_NAME)


app = FastAPI(
    title="ISLI Skills",
    version="0.1.0",
    lifespan=lifespan,
)
instrument_fastapi(app, SERVICE_NAME)
app.include_router(browser_router)


async def execute_dynamic_code(
    code: str,
    payload: dict[str, Any],
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Internal helper to execute dynamic skill code in a restricted sandbox."""
    validate_skill_code(code)

    # Inject workspace-installed packages into sys.path if agent_id is known
    _injected_path: str | None = None
    if agent_id:
        import sys
        pip_target = f"/workspaces/agents/{agent_id}/.pip-packages"
        if os.path.isdir(pip_target) and pip_target not in sys.path:
            sys.path.insert(0, pip_target)
            _injected_path = pip_target
            logger.debug("skills.dynamic.injected_pip_path", agent_id=agent_id, path=pip_target)

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

        run_func = namespace.get("run")
        if not run_func:
            raise AttributeError("Dynamic skill must define a 'run' function")

        import asyncio
        if asyncio.iscoroutinefunction(run_func):
            result = await run_func(payload)
        else:
            result = run_func(payload)

        return result
    except Exception as exc:
        logger.error("skills.dynamic.execution_failed", error=str(exc))
        raise exc
    finally:
        if _injected_path:
            import sys
            with contextlib.suppress(ValueError):
                sys.path.remove(_injected_path)
            logger.debug("skills.dynamic.removed_pip_path", path=_injected_path)


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
async def list_skills(auth: dict = Depends(require_internal_auth)):
    return {"skills": list(SKILL_REGISTRY.values())}


@app.post("/register", status_code=201)
@app.post("/skills", status_code=201)
async def register_skill(skill: RegisterSkill, auth: dict = Depends(require_internal_auth)):
    if skill.name in SKILL_REGISTRY:
        # Update existing skill
        logger.info("skills.updating", name=skill.name)
        existing = SKILL_REGISTRY[skill.name]
        skill.usage_count = existing.get("usage_count", 0)
        skill.last_used_at = existing.get("last_used_at")
        skill.created_at = existing.get("created_at")
    
    if not skill.created_at:
        skill.created_at = datetime.now(timezone.utc).isoformat()
    
    SKILL_REGISTRY[skill.name] = skill.model_dump()
    save_registry()
    logger.info("skills.registered", name=skill.name, endpoint=skill.endpoint)
    return {"status": "registered", "skill": skill.model_dump()}


@app.post("/update")
async def update_skill(body: UpdateSkillRequest, auth: dict = Depends(require_internal_auth)):
    if body.name not in SKILL_REGISTRY:
        raise HTTPException(status_code=404, detail=f"Skill '{body.name}' not found")

    existing = SKILL_REGISTRY[body.name]
    updated = dict(existing)
    if body.endpoint is not None:
        updated["endpoint"] = body.endpoint
    if body.workspace_path is not None:
        updated["workspace_path"] = body.workspace_path
    if body.agent_id is not None:
        updated["agent_id"] = body.agent_id
    if body.health_endpoint is not None:
        updated["health_endpoint"] = body.health_endpoint
    if body.description is not None:
        updated["description"] = body.description
    if body.category is not None:
        updated["category"] = body.category

    SKILL_REGISTRY[body.name] = updated
    save_registry()
    logger.info("skills.updated", name=body.name)
    return {"status": "updated", "skill": updated}


@app.post("/test")
async def test_skill(request: TestSkillRequest, auth: dict = Depends(require_internal_auth)):
    """Dry-run endpoint for testing dynamic skill code without registration."""
    logger.info("skills.test_request")
    try:
        result = await execute_dynamic_code(request.code, request.payload)
        return {"success": True, "result": result}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@app.post("/debug")
async def debug_skill(request: DebugRequest, auth: dict = Depends(require_internal_auth)):
    """Interactive debugger endpoint with breakpoints, trace, and variable inspection."""
    logger.info("skills.debug_request", mode=request.mode, breakpoints=len(request.breakpoints))
    try:
        result = await execute_with_trace(
            code=request.code,
            payload=request.payload,
            breakpoints=request.breakpoints,
            mode=request.mode,
            max_steps=request.max_steps,
            max_trace_size=request.max_trace_size,
            only_changes=request.only_changes,
            include_locals=request.include_locals,
            include_globals=request.include_globals,
            watch_expressions=request.watch_expressions,
            stdin=request.stdin,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("skills.debug_execution_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Debugger execution error: {exc}")


@app.post("/skills/{name}/usage")
async def record_usage(name: str, auth: dict = Depends(require_internal_auth)):
    """Increment usage metrics for a skill. Called by Core proxy for external skills."""
    skill = SKILL_REGISTRY.get(name)
    if not skill:
        # Auto-register external skill if not present to start tracking
        skill = {
            "name": name,
            "type": "external",
            "usage_count": 0,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    
    skill["usage_count"] = skill.get("usage_count", 0) + 1
    skill["last_used_at"] = datetime.now(timezone.utc).isoformat()
    SKILL_REGISTRY[name] = skill
    save_registry()
    return {"status": "recorded", "usage_count": skill["usage_count"]}


@app.get("/skills/{name}/health")
async def skill_health(name: str, auth: dict = Depends(require_internal_auth)):
    skill = SKILL_REGISTRY.get(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return {"status": "ok", "skill": name, "endpoint": skill.get("endpoint")}


@app.post("/browse")
async def browse(request: BrowseRequest, auth: dict = Depends(require_internal_auth)):
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


@app.post("/fetch")
async def fetch(request: FetchRequest, auth: dict = Depends(require_internal_auth)):
    """Standard web-fetch endpoint for agents."""
    logger.info("skills.fetch", url=request.url, agent_id=request.agent_id)
    result = await browse_url(url=request.url)
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@app.post("/search")
async def search(request: SearchRequest, auth: dict = Depends(require_internal_auth)):
    """Web search endpoint via SearXNG."""
    logger.info("skills.search", query=request.query, max_results=request.max_results)
    
    import httpx
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            params = {
                "q": request.query,
                "format": "json",
                "safesearch": 1
            }
            resp = await client.get(SEARXNG_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
            
            results = []
            for res in data.get("results", [])[:request.max_results]:
                results.append({
                    "title": res.get("title"),
                    "url": res.get("url"),
                    "snippet": res.get("content") or res.get("snippet")
                })
            
            return {"success": True, "query": request.query, "results": results}
            
    except Exception as exc:
        logger.error("skills.search_failed", query=request.query, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Web search failed: {exc}")


@app.post("/summarize")
async def summarize(request: SummarizeRequest, auth: dict = Depends(require_internal_auth)):
    """Summarize text via Keeper. Falls back to raw text if Keeper is unreachable."""
    logger.info("skills.summarize", text_len=len(request.text), max_length=request.max_length)
    token = create_internal_token("isli-skills", scopes=["skill:invoke"], expires_minutes=5)
    headers = {"X-Internal-Auth": token, "Content-Type": "application/json"}
    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{KEEPER_URL}/summarize",
                headers=headers,
                json={"text": request.text, "max_length": request.max_length},
            )
            resp.raise_for_status()
            data = resp.json()
            return {"summary": data.get("summary", ""), "model": data.get("model", "")}
    except httpx.RequestError as exc:
        logger.warning("skills.summarize_keeper_unreachable", error=str(exc))
        return {"summary": request.text, "model": "fallback", "note": "Keeper unreachable; returning raw text"}
    except httpx.HTTPStatusError as exc:
        logger.error("skills.summarize_keeper_error", status=exc.response.status_code, error=str(exc))
        return {"summary": request.text, "model": "fallback", "note": "Keeper error; returning raw text"}


@app.post("/embed")
async def embed(request: EmbedRequest, auth: dict = Depends(require_internal_auth)):
    """Generate text embeddings via Keeper. Falls back to empty embedding if Keeper is unreachable."""
    logger.info("skills.embed", input_len=len(request.input))
    token = create_internal_token("isli-skills", scopes=["skill:invoke"], expires_minutes=5)
    headers = {"X-Internal-Auth": token, "Content-Type": "application/json"}
    try:
        import httpx
        payload: dict[str, Any] = {"input": request.input}
        if request.model:
            payload["model"] = request.model
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{KEEPER_URL}/embed",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return {"embedding": data.get("embedding", []), "model": data.get("model", "")}
    except httpx.RequestError as exc:
        logger.warning("skills.embed_keeper_unreachable", error=str(exc))
        return {"embedding": [], "model": "fallback", "note": "Keeper unreachable; returning empty embedding"}
    except httpx.HTTPStatusError as exc:
        logger.error("skills.embed_keeper_error", status=exc.response.status_code, error=str(exc))
        return {"embedding": [], "model": "fallback", "note": "Keeper error; returning empty embedding"}


@app.post("/db-query")
async def db_query(request: DbQueryRequest, auth: dict = Depends(require_internal_auth)):
    """Execute a read-only SQL query against the configured database."""
    logger.info("skills.db_query", agent_id=request.agent_id, query_preview=request.query[:60])
    settings = get_settings()

    if not settings.database_url:
        raise HTTPException(status_code=503, detail="Database not configured for db-query skill")

    allowed_schemas = {s.strip() for s in settings.db_query_allowed_schemas.split(",") if s.strip()}
    if request.schema_name:
        allowed_schemas = {request.schema_name}
    validate_query(request.query, allowed_schemas=allowed_schemas)

    max_rows = min(request.max_rows, settings.db_query_max_rows)
    result = await execute_query(
        sql=request.query,
        database_url=settings.database_url,
        max_rows=max_rows,
        timeout_seconds=settings.db_query_timeout_seconds,
    )
    return result


@app.post("/skills/{name}/invoke")
async def invoke_skill(name: str, body: InvokeSkill, auth: dict = Depends(require_internal_auth)):
    skill = SKILL_REGISTRY.get(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

    # Track usage
    skill["usage_count"] = skill.get("usage_count", 0) + 1
    skill["last_used_at"] = datetime.now(timezone.utc).isoformat()
    SKILL_REGISTRY[name] = skill
    save_registry()

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
                    json={"agent_id": skill["agent_id"], "path": skill["workspace_path"]},
                    headers={"X-Internal-Auth": create_internal_token("isli-skills", scopes=["skill:invoke"], expires_minutes=5)},
                )
                resp.raise_for_status()
                code = resp.json().get("content")
        except Exception as exc:
            logger.error("skills.dynamic.fetch_failed", name=name, error=str(exc))
            raise HTTPException(status_code=502, detail=f"Failed to fetch dynamic skill code: {exc}")

        # 2. Execute code in-memory
        try:
            result = await execute_dynamic_code(code, body.payload, agent_id=skill["agent_id"])
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
