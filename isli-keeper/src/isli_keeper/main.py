import asyncio
import hashlib
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import structlog
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from .auth import require_internal_auth
from .config import get_settings
from .db import close_db, get_recent_memories, get_relevant_memories, init_db
from .metrics import get_metrics
from .model_manager import ModelManager
from .ollama_client import OllamaClient
from .priority_queue import get_priority_manager, P0, P1, P2, P3
from .prompts_loader import get_prompts, clear_prompts_cache
from .telemetry import get_trace_id, instrument_fastapi

SERVICE_NAME = "isli-keeper"

logger = structlog.get_logger()

settings = get_settings()
DEFAULT_EMBED_MODEL = settings.ollama_embed_model
DEFAULT_GEN_MODEL = settings.ollama_gen_model

model_manager = ModelManager()
priority_manager = get_priority_manager()

# In-memory LRU cache for /intent/classify
_INTENT_CLASSIFY_CACHE: dict[str, tuple[dict, float, float]] = {}
_INTENT_CACHE_MAX_SIZE = 500
_INTENT_CACHE_TTL_SECONDS = 60.0

def get_gen_model() -> str:
    return model_manager.get_model("gen")

def get_embed_model() -> str:
    return model_manager.get_model("embed")


def _extract_json_block(text: str) -> str | None:
    """Find the first balanced JSON object in text by brace depth."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _compress_activity_log(
    entries: list[tuple[datetime, str]],
    max_entries: int = 20,
    max_chars: int = 2000,
) -> str:
    """Compress timestamped activity entries for the heartbeat validator prompt.

    Deduplicates consecutive entries with identical *summary* text (ignoring
    timestamp), prefixes each with its timestamp, and truncates from the end.
    Entries older than 24 hours are dropped. If the most recent entry is older
    than 1 hour, the agent is considered idle and no anomaly is possible.
    """
    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_1h = now - timedelta(hours=1)

    # Filter to entries within 24 hours
    recent_entries = [(ts, s) for ts, s in entries if ts >= cutoff_24h]

    # Also guard against a single 23-hour-old entry leaking stale data
    last_activity = max((ts for ts, _ in entries), default=None)
    if not recent_entries or (last_activity and last_activity < cutoff_1h):
        age_text = ""
        if last_activity:
            hours_ago = int((now - last_activity).total_seconds() // 3600)
            age_text = f" ({hours_ago}h ago)"
        return f"[No recent activity{age_text}] Agent is idle — no anomaly possible."

    # Deduplicate consecutive identical summaries
    deduped: list[tuple[datetime, str]] = []
    prev_summary: str | None = None
    count = 1
    first_ts = None
    for ts, summary in recent_entries:
        if summary == prev_summary:
            count += 1
        else:
            if prev_summary is not None and first_ts is not None:
                suffix = f" (repeated {count}x)" if count > 1 else ""
                deduped.append((first_ts, f"{prev_summary}{suffix}"))
            prev_summary = summary
            count = 1
            first_ts = ts
    if prev_summary and first_ts is not None:
        suffix = f" (repeated {count}x)" if count > 1 else ""
        deduped.append((first_ts, f"{prev_summary}{suffix}"))

    # Take last N unique entries (oldest first in the list, but entries come newest-first)
    # Reverse so oldest appears at top of prompt, then take last max_entries
    deduped.reverse()
    recent = deduped[-max_entries:]

    # Format with ISO-ish timestamps
    lines = [f"[{ts.strftime('%Y-%m-%d %H:%M')}] {text}" for ts, text in recent]

    result = "\n".join(lines)
    return result[-max_chars:] if len(result) > max_chars else result


async def _ollama_generate_task(model: str, prompt: str, timeout: float | None = None, format: str | None = None) -> dict:
    async with OllamaClient().session() as client:
        return await client.generate(model, prompt, timeout=timeout, format=format)


async def _ollama_embed_task(model: str, input_text: str) -> list[float]:
    async with OllamaClient().session() as client:
        return await client.embed(model, input_text)


async def _generate_with_ollama(
    prompt: str,
    model: str,
    agent_id: str | None = None,
    endpoint: str = "generate",
    timeout: float | None = None,
    format: str | None = None,
    priority: int = P2,
) -> dict:
    # Default timeouts by priority if not specified
    if timeout is None:
        if priority == P0:
            timeout = 45.0
        elif priority <= P2:
            timeout = 120.0
        else:
            timeout = 300.0

    metadata = {
        "agent_id": agent_id,
        "endpoint": endpoint,
        "model": model,
        "prompt": prompt[:2000],
    }

    metrics = get_metrics()
    metrics.start_request()
    try:
        return await priority_manager.submit(
            priority, timeout, _ollama_generate_task, metadata, model, prompt, timeout, format
        )
    except asyncio.TimeoutError:
        logger.error("keeper.timeout", endpoint=endpoint, timeout=timeout, agent_id=agent_id)
        raise HTTPException(status_code=503, detail=f"Keeper timeout ({timeout}s) for {endpoint}")
    except RuntimeError as e:
        if "depth exceeded" in str(e):
            raise HTTPException(status_code=429, detail=str(e))
        raise
    except Exception as exc:
        logger.error("keeper.inference_error", endpoint=endpoint, error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))


async def _keep_model_warm():
    """Send a lightweight generate request every 60s to keep the model in VRAM."""
    while True:
        await asyncio.sleep(60)
        try:
            async with OllamaClient().session() as client:
                await client.generate(
                    model=get_gen_model(),
                    prompt=".",
                    options={"num_predict": 1},
                    keep_alive=-1,
                )
        except Exception:
            pass  # non-critical background task


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("keeper.startup", service=SERVICE_NAME)
    await init_db()
    from .session_prep import init_pii_vault
    await init_pii_vault()
    priority_manager.start()
    warm_task = asyncio.create_task(_keep_model_warm())
    try:
        yield
    finally:
        warm_task.cancel()
        try:
            await warm_task
        except asyncio.CancelledError:
            pass
        await priority_manager.stop()
        await close_db()
        logger.info("keeper.shutdown", service=SERVICE_NAME)


app = FastAPI(
    title="ISLI Keeper",
    version="0.1.0",
    lifespan=lifespan,
)
instrument_fastapi(app, SERVICE_NAME)


class EmbedRequest(BaseModel):
    input: str
    model: str = Field(default_factory=get_embed_model)
    agent_id: str | None = None


class SummarizeRequest(BaseModel):
    text: str
    max_length: int = 256
    agent_id: str | None = None


class GenerateRequest(BaseModel):
    prompt: str
    model: str = Field(default_factory=get_gen_model)
    options: dict[str, Any] | None = None
    agent_id: str | None = None


class ContextInjectRequest(BaseModel):
    agent_id: str
    session_id: str | None = None
    task_description: str | None = None
    agent_name: str | None = None
    agent_description: str | None = None
    memory_similarity_threshold: float = 0.4
    known_agent_ids: list[str] | None = None


class IntentClassifyRequest(BaseModel):
    user_message: str
    available_skills: list[dict[str, str]]  # [{"name": "...", "hint": "..."}]
    agent_id: str | None = None


class IntentClassifyResponse(BaseModel):
    relevant_skills: list[str]
    reason: str = ""
    confidence: float = 0.0


class ModelRouteRequest(BaseModel):
    agent_id: str
    task_description: str
    complexity_score: int
    complexity_tier: str
    secondary_models: list[dict[str, Any]]
    default_provider: str | None = None
    default_model: str | None = None


class ModelRouteResponse(BaseModel):
    recommended_provider: str
    recommended_model_id: str
    reason: str


class HeartbeatRequest(BaseModel):
    agent_id: str
    status: str
    anomaly: str | None = None


class HeartbeatValidateRequest(BaseModel):
    agent_id: str
    heartbeat_at: str
    consecutive_idle_beats: int = 0
    current_task_id: str | None = None


class ScrubRequest(BaseModel):
    text: str
    agent_id: str | None = None


class UnscrubRequest(BaseModel):
    text: str
    mapping: dict[str, str]
    agent_id: str | None = None


class CleanRequest(BaseModel):
    raw_data: str
    extraction_goal: str
    agent_id: str | None = None


class VerifyLogicRequest(BaseModel):
    text: str
    context: str | None = None
    agent_id: str | None = None


@app.get("/health")
async def health():
    trace_id = get_trace_id()
    return {"status": "ok", "service": SERVICE_NAME, "trace_id": trace_id}


@app.get("/ready")
async def ready():
    ollama_ok = False
    try:
        async with OllamaClient().session() as client:
            await client.list_models()
        ollama_ok = True
    except Exception as exc:
        logger.warning("keeper.ollama_not_ready", error=str(exc))

    return {
        "status": "ready" if ollama_ok else "degraded",
        "service": SERVICE_NAME,
        "ollama": "ok" if ollama_ok else "fail",
    }


@app.get("/live")
async def live():
    return {"status": "alive", "service": SERVICE_NAME}


@app.post("/embed")
async def embed(
    req: EmbedRequest,
    request: Request,
    auth: dict = Depends(require_internal_auth),
):
    agent_id = req.agent_id or request.headers.get("X-Agent-ID")
    metadata = {
        "agent_id": agent_id,
        "endpoint": "embed",
        "model": req.model,
        "prompt": req.input[:100],
    }

    metrics = get_metrics()
    metrics.start_request()
    try:
        # Embeddings are usually background (P3)
        embedding = await priority_manager.submit(
            P3, 300.0, _ollama_embed_task, metadata, req.model, req.input
        )
        return {"embedding": embedding, "model": req.model}
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail="Keeper timeout (300s) for embed")
    except RuntimeError as e:
        if "depth exceeded" in str(e):
            raise HTTPException(status_code=429, detail=str(e))
        raise
    except Exception as exc:
        logger.error("keeper.embed_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/summarize")
async def summarize(
    req: SummarizeRequest,
    request: Request,
    auth: dict = Depends(require_internal_auth),
):
    agent_id = req.agent_id or request.headers.get("X-Agent-ID")
    prompt = get_prompts()["keeper"]["summarize"].format(
        max_length=req.max_length, text=req.text
    )
    try:
        result = await _generate_with_ollama(
            prompt, model=get_gen_model(), agent_id=agent_id, endpoint="summarize"
        )
        summary = result.get("response", "")
        return {"summary": summary, "model": get_gen_model()}
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        logger.error("keeper.summarize_failed", error=str(exc))
        raise HTTPException(status_code=503, detail="Keeper LLM unavailable: Ollama unreachable")
    except Exception as exc:
        logger.error("keeper.summarize_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))


class JournalUpdateRequest(BaseModel):
    session_id: str
    old_journal: str | None = None
    recent_messages: list[dict[str, Any]]
    agent_id: str | None = None


@app.post("/journal/update")
async def journal_update(
    req: JournalUpdateRequest,
    request: Request,
    auth: dict = Depends(require_internal_auth),
):
    agent_id = req.agent_id or request.headers.get("X-Agent-ID")
    recent_messages = "\n".join(
        f"{msg.get('role', 'user')}: {msg.get('content', '')}"
        for msg in req.recent_messages
    )
    prompt = get_prompts()["keeper"]["journal_update"].format(
        old_journal=req.old_journal or "No previous journal.",
        recent_messages=recent_messages,
    )

    try:
        result = await _generate_with_ollama(
            prompt,
            model=get_gen_model(),
            agent_id=agent_id,
            endpoint="journal/update",
            priority=P3,
        )
        updated_journal = result.get("response", "")
        return {"journal": updated_journal, "model": get_gen_model()}
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        logger.error("keeper.journal_update_failed", error=str(exc))
        raise HTTPException(status_code=503, detail="Keeper LLM unavailable: Ollama unreachable")
    except Exception as exc:
        logger.error("keeper.journal_update_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/context/inject")
async def context_inject(req: ContextInjectRequest, auth: dict = Depends(require_internal_auth)):
    metrics = get_metrics()
    metrics.start_request()
    start = time.monotonic()
    try:
        # 1. Fetch episodic memories (Tier 2) - use semantic search if task description is provided
        memories = []
        if req.task_description:
            metadata = {
                "agent_id": req.agent_id,
                "endpoint": "context/inject:embed",
                "model": get_embed_model(),
                "prompt": req.task_description[:100],
            }
            try:
                embedding = await priority_manager.submit(
                    P0, 45.0, _ollama_embed_task, metadata, get_embed_model(), req.task_description
                )
                memories = await get_relevant_memories(
                    req.agent_id, embedding, threshold=req.memory_similarity_threshold
                )

                # Conditional Fallback: If semantic search ran but found nothing above threshold,
                # fall back to recent memories BUT cap at 3 and log it.
                if not memories:
                    memories = await get_recent_memories(req.agent_id, limit=3)
                    logger.warning("keeper.semantic_search_empty_fallback", agent_id=req.agent_id)
            except Exception as exc:
                logger.warning("keeper.semantic_search_failed", error=str(exc))
                # Fallback on error: cap at 3
                memories = await get_recent_memories(req.agent_id, limit=3)
        else:
            # No task description: No context by default (unlike previous unconditional 5 recent)
            memories = []

        # 2. Fetch session data (Tier 1) - including the structured journal
        journal = ""
        last_3_messages = ""
        if req.session_id:
            from .db import get_session_data
            session_data = await get_session_data(req.session_id)
            journal = session_data.get("journal") or ""
            messages = session_data.get("messages") or []
            if messages:
                # Last 3 messages for immediate raw context
                raw_msgs = messages[-3:]
                last_3_messages = "\n".join([f"{m.get('role', 'user')}: {m.get('content', '')}" for m in raw_msgs])

        # 3. Fast Synthesis: Just assemble the pre-computed pieces
        # No 7B generation here anymore - we use the pre-computed journal
        context_parts = []

        # Prepend Agent Identity if available
        identity_parts = []
        if req.agent_name:
            identity_parts.append(f"Name: {req.agent_name}")
        if req.agent_id:
            identity_parts.append(f"ID: {req.agent_id}")
        if req.agent_description:
            identity_parts.append(f"Description: {req.agent_description}")

        if identity_parts:
            identity_block = "=== AGENT IDENTITY ===\n" + "\n".join(identity_parts)
            context_parts.append(identity_block)

        if journal:
            context_parts.append(f"=== SESSION JOURNAL ===\n{journal}")

        if last_3_messages:
            context_parts.append(f"=== RECENT MESSAGES ===\n{last_3_messages}")

        if memories:
            memories_text = "\n".join([f"- {m}" for m in memories])
            context_parts.append(f"=== HISTORICAL MEMORIES ===\n{memories_text}")

        if req.known_agent_ids:
            peer_block = (
                "=== PEER AGENTS ===\n"
                "You can delegate tasks to the following agents via the Kanban board:\n"
            )
            for peer_id in req.known_agent_ids:
                peer_block += f"- {peer_id}\n"
            peer_block += (
                "\nWhen delegating, use create_task and set assignee to the target agent ID."
            )
            context_parts.append(peer_block)

        if not context_parts:
            metrics.record_inference(
                agent_id=req.agent_id,
                endpoint="context/inject",
                model="retrieval-only",
                latency_ms=(time.monotonic() - start) * 1000,
                prompt=req.task_description or "",
                completion="No previous context found.",
                status="success",
            )
            return {
                "context_summary": "No previous context found.",
                "relevant_memories": [],
                "model": "retrieval-only"
            }

        context_summary = "\n\n".join(context_parts)

        metrics.record_inference(
            agent_id=req.agent_id,
            endpoint="context/inject",
            model="retrieval-only",
            latency_ms=(time.monotonic() - start) * 1000,
            prompt=req.task_description or "",
            completion=context_summary,
            status="success",
        )
        return {
            "context_summary": context_summary,
            "relevant_memories": memories,
            "model": "retrieval-only"
        }
    except Exception as exc:
        latency = (time.monotonic() - start) * 1000
        metrics.record_inference(
            agent_id=req.agent_id,
            endpoint="context/inject",
            model="retrieval-only",
            latency_ms=latency,
            prompt=req.task_description or "",
            status="error",
            error=f"{type(exc).__name__}: {str(exc)[:200]}",
        )
        logger.error("keeper.context_inject_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))


# ── Intent classifier cache helpers ──────────────────────────────────────────

def _intent_cache_key(agent_id: str | None, message: str, skill_names: list[str]) -> str:
    payload = {
        "agent_id": agent_id or "",
        "message_prefix": message[:120],
        "skills": sorted(skill_names),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _intent_cache_get(key: str) -> dict | None:
    now = time.monotonic()
    entry = _INTENT_CLASSIFY_CACHE.get(key)
    if entry:
        result, expires_at, last_accessed = entry
        if expires_at > now:
            # Update LRU timestamp
            _INTENT_CLASSIFY_CACHE[key] = (result, expires_at, now)
            return result
    return None


def _intent_cache_set(key: str, result: dict) -> None:
    now = time.monotonic()
    # Evict oldest 10% if at capacity
    if len(_INTENT_CLASSIFY_CACHE) >= _INTENT_CACHE_MAX_SIZE:
        sorted_items = sorted(
            _INTENT_CLASSIFY_CACHE.items(),
            key=lambda kv: kv[1][2],  # last_accessed
        )
        evict_count = max(1, _INTENT_CACHE_MAX_SIZE // 10)
        for evict_key, _ in sorted_items[:evict_count]:
            del _INTENT_CLASSIFY_CACHE[evict_key]
    _INTENT_CLASSIFY_CACHE[key] = (
        result,
        now + _INTENT_CACHE_TTL_SECONDS,
        now,
    )


INTENT_CLASSIFY_PROMPT = """You are a lightweight intent classifier for an AI agent's skill toolkit.

Given the user's message and the list of available skills below, select ONLY the skills that are directly relevant to answering the user's request.

Rules:
- Return ONLY a JSON object with keys "relevant_skills" (array of strings), "reason" (one sentence), and "confidence" (float 0.0–1.0).
- If the intent is unclear, broad, or conversational, return an empty array and confidence 0.0.
- Do NOT include skills just because they sound related; only include skills that the agent would actually CALL.

Available skills:
{available_skills}

User message:
---
{user_message}
---

Respond ONLY with JSON:
{{"relevant_skills": ["skill-name-1", ...], "reason": "...", "confidence": 0.85}}
"""


@app.post("/intent/classify")
async def intent_classify(req: IntentClassifyRequest, auth: dict = Depends(require_internal_auth)):
    """Lightweight skill-intent classifier. Returns relevant skill names for a user message."""
    metrics = get_metrics()
    start = time.monotonic()
    agent_id = req.agent_id

    skill_names = [s["name"] for s in req.available_skills]
    cache_key = _intent_cache_key(agent_id, req.user_message, skill_names)
    cached = _intent_cache_get(cache_key)
    if cached:
        logger.info("keeper.intent_classify.cache_hit", agent_id=agent_id)
        return cached

    skills_block = "\n".join(
        f"- {s['name']}: {s.get('hint', '')}" for s in req.available_skills
    )
    prompt = INTENT_CLASSIFY_PROMPT.format(
        available_skills=skills_block,
        user_message=req.user_message[:500],
    )

    try:
        result = await _generate_with_ollama(
            prompt,
            model=get_gen_model(),
            agent_id=agent_id,
            endpoint="intent/classify",
            format="json",
            priority=P1,
            timeout=45.0,
        )
        raw_output = result.get("response", "").strip()
        block = _extract_json_block(raw_output)
        if block:
            verdict = json.loads(block)
            relevant_skills = verdict.get("relevant_skills", [])
            if not isinstance(relevant_skills, list):
                relevant_skills = []
            # Validate that returned skills exist in the input set
            valid_names = set(skill_names)
            relevant_skills = [s for s in relevant_skills if isinstance(s, str) and s in valid_names]
            reason = verdict.get("reason", "")
            confidence = float(verdict.get("confidence", 0.0))
        else:
            relevant_skills = []
            reason = "No JSON block found in SLM output"
            confidence = 0.0
    except Exception as exc:
        logger.error("keeper.intent_classify_failed", error=str(exc), agent_id=agent_id)
        # Safe fallback: return all skills
        relevant_skills = skill_names
        reason = f"Classifier failed ({type(exc).__name__}); returning all skills as fallback"
        confidence = 0.0

    latency = (time.monotonic() - start) * 1000
    metrics.record_inference(
        agent_id=agent_id or "system",
        endpoint="intent/classify",
        model=get_gen_model(),
        latency_ms=latency,
        prompt=req.user_message[:80],
        completion=json.dumps(relevant_skills),
        status="success" if confidence > 0 else "fallback",
    )
    logger.info(
        "keeper.intent_classified",
        agent_id=agent_id,
        relevant_skills=relevant_skills,
        confidence=confidence,
        latency_ms=latency,
    )

    response = {
        "relevant_skills": relevant_skills,
        "reason": reason,
        "confidence": confidence,
    }
    _intent_cache_set(cache_key, response)
    return response


def _format_model_list(models: list[dict]) -> str:
    """Format secondary models into prose for the Ollama prompt."""
    lines = []
    for i, m in enumerate(models, 1):
        tier = m.get("cost_tier", "unknown")
        lines.append(
            f"{i}. {m['model_id']} ({m.get('label', 'no label')}) — "
            f"{m.get('description', 'no description')}; tier={tier}"
        )
    return "\n".join(lines) if lines else "(none)"


@app.post("/model/route")
async def model_route(req: ModelRouteRequest, auth: dict = Depends(require_internal_auth)):
    """Keeper-side model router: given a task and available models, pick the best one."""
    metrics = get_metrics()
    start = time.monotonic()

    model_list = _format_model_list(req.secondary_models)
    prompt = get_prompts()["keeper"]["model_router"].format(
        task_description=req.task_description,
        complexity_score=req.complexity_score,
        complexity_tier=req.complexity_tier,
        model_list=model_list,
        default_model=req.default_model or "(none)",
    )

    try:
        result = await _generate_with_ollama(
            prompt,
            model=get_gen_model(),
            agent_id=req.agent_id,
            endpoint="model/route",
            format="json",
            priority=P0,
        )
        resp_text = result.get("response", "").strip()
        block = _extract_json_block(resp_text)

        if block:
            verdict = json.loads(block)
            recommended_model_id = verdict.get("recommended_model_id")
            reason = verdict.get("reason", "No reason provided")

            # Validate that the recommended model exists in the secondary models list
            valid_ids = {m["model_id"] for m in req.secondary_models}
            if recommended_model_id not in valid_ids:
                logger.warning(
                    "keeper.model_route_invalid_model",
                    agent_id=req.agent_id,
                    recommended=recommended_model_id,
                    valid=list(valid_ids),
                    fallback=req.default_model,
                )
                recommended_model_id = req.default_model
                reason = f"Keeper returned unknown model; falling back to default ({req.default_model})"

            # Resolve provider from secondary_models or default
            provider = req.default_provider or ""
            for m in req.secondary_models:
                if m["model_id"] == recommended_model_id:
                    provider = m.get("provider", provider)
                    break

            latency = (time.monotonic() - start) * 1000
            metrics.record_inference(
                agent_id=req.agent_id,
                endpoint="model/route",
                model=get_gen_model(),
                latency_ms=latency,
                prompt=prompt[:200],
                completion=resp_text[:200],
                status="success",
            )
            return {
                "recommended_provider": provider,
                "recommended_model_id": recommended_model_id,
                "reason": reason,
            }

        # No JSON block found
        logger.warning("keeper.model_route_no_json", agent_id=req.agent_id, raw=resp_text[:200])
    except Exception as exc:
        latency = (time.monotonic() - start) * 1000
        metrics.record_inference(
            agent_id=req.agent_id,
            endpoint="model/route",
            model=get_gen_model(),
            latency_ms=latency,
            prompt=prompt[:200],
            status="error",
            error=f"{type(exc).__name__}: {str(exc)[:200]}",
        )
        logger.error("keeper.model_route_failed", agent_id=req.agent_id, error=str(exc))

    # Fail-open: return the default model
    return {
        "recommended_provider": req.default_provider or "",
        "recommended_model_id": req.default_model or "",
        "reason": "Keeper routing failed or returned invalid JSON; falling back to default model",
    }


@app.post("/generate")
async def generate(
    req: GenerateRequest,
    request: Request,
    auth: dict = Depends(require_internal_auth),
):
    agent_id = req.agent_id or request.headers.get("X-Agent-ID")
    try:
        result = await _generate_with_ollama(req.prompt, model=req.model, agent_id=agent_id, endpoint="generate")
        return result
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        logger.error("keeper.generate_failed", error=str(exc))
        raise HTTPException(status_code=503, detail="Keeper LLM unavailable: Ollama unreachable")
    except Exception as exc:
        logger.error("keeper.generate_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))

class PullRequest(BaseModel):
    slot: str
    model_name: str


class ActivateRequest(BaseModel):
    slot: str
    model_name: str


class RemoveRequest(BaseModel):
    model_name: str


@app.post("/admin/activate")
async def admin_activate(
    req: ActivateRequest,
    auth: dict = Depends(require_internal_auth),
):
    if req.slot not in model_manager.config:
        raise HTTPException(status_code=400, detail=f"Invalid slot: {req.slot}")
    try:
        async with OllamaClient().session() as client:
            exists = await client.model_exists(req.model_name)
        if not exists:
            raise HTTPException(
                status_code=404, detail=f"Model {req.model_name} is not available in Ollama"
            )
        model_manager.set_model(req.slot, req.model_name)
        return {
            "status": "ok",
            "slot": req.slot,
            "model": req.model_name,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("keeper.admin_activate_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/admin/remove")
async def admin_remove(
    req: RemoveRequest,
    auth: dict = Depends(require_internal_auth),
):
    try:
        async with OllamaClient().session() as client:
            exists = await client.model_exists(req.model_name)
        if not exists:
            raise HTTPException(
                status_code=404, detail=f"Model {req.model_name} is not available in Ollama"
            )

        # Check if the model is active for any slot
        was_active = False
        affected_slot = None
        for slot, active_model in model_manager.config.items():
            if active_model == req.model_name:
                was_active = True
                affected_slot = slot
                break

        if was_active and affected_slot:
            settings = get_settings()
            fallback = (
                settings.ollama_gen_model
                if affected_slot == "gen"
                else settings.ollama_embed_model
            )
            async with OllamaClient().session() as client:
                fallback_exists = await client.model_exists(fallback)
            if not fallback_exists:
                raise HTTPException(
                    status_code=409,
                    detail="Cannot remove active model: fallback default not available",
                )

        # Delete from Ollama
        async with OllamaClient().session() as client:
            await client.delete_model(req.model_name)

        # Reset active slot if needed
        if was_active and affected_slot:
            fallback = (
                get_settings().ollama_gen_model
                if affected_slot == "gen"
                else get_settings().ollama_embed_model
            )
            model_manager.set_model(affected_slot, fallback)

        return {
            "status": "ok",
            "removed": req.model_name,
            "was_active": was_active,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("keeper.admin_remove_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/admin/reload-prompts")
async def reload_prompts(auth: dict = Depends(require_internal_auth)):
    clear_prompts_cache()
    return {"status": "ok", "reloaded": True}


class AdminConfigUpdateRequest(BaseModel):
    num_ctx: int | None = None
    num_batch: int | None = None


@app.get("/admin/config")
async def admin_config(auth: dict = Depends(require_internal_auth)):
    return {
        "config": {
            "gen": model_manager.get_model("gen"),
            "embed": model_manager.get_model("embed"),
            "num_ctx": model_manager.config.get("num_ctx", 4096),
            "num_batch": model_manager.config.get("num_batch", 512),
        }
    }


@app.post("/admin/config")
async def admin_config_update(
    req: AdminConfigUpdateRequest,
    auth: dict = Depends(require_internal_auth),
):
    try:
        updated = model_manager.set_generation_options(
            num_ctx=req.num_ctx,
            num_batch=req.num_batch,
        )
        return {
            "status": "ok",
            "config": {
                "gen": model_manager.get_model("gen"),
                "embed": model_manager.get_model("embed"),
                **updated,
            },
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("keeper.admin_config_update_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/admin/pull")
async def admin_pull(
    req: PullRequest,
    auth: dict = Depends(require_internal_auth),
):
    try:
        async with OllamaClient().session() as client:
            result = await client.pull_model(req.model_name)
        model_manager.set_model(req.slot, req.model_name)
        return {
            "status": "ok",
            "slot": req.slot,
            "model": req.model_name,
            "ollama_result": result,
        }
    except Exception as exc:
        logger.error("keeper.admin_pull_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/models")
async def list_models(auth: dict = Depends(require_internal_auth)):
    try:
        async with OllamaClient().session() as client:
            models = await client.list_models()
        return {"models": models}
    except Exception as exc:
        logger.error("keeper.list_models_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/heartbeat")
async def heartbeat(req: HeartbeatRequest, auth: dict = Depends(require_internal_auth)):
    anomaly_found = req.anomaly

    # Run LLM-based anomaly detection if status is unusual or requested
    if not anomaly_found and req.status not in ("online", "idle"):
        try:
            # Fetch recent activity for context
            from .db import get_recent_memories
            memories = await get_recent_memories(req.agent_id, limit=3)
            activity_text = "\n".join(memories)

            prompt = get_prompts()["keeper"]["heartbeat_anomaly"].format(
                agent_id=req.agent_id,
                status=req.status,
                activity=activity_text,
            )

            result = await _generate_with_ollama(
                prompt,
                model=get_gen_model(),
                agent_id=req.agent_id,
                endpoint="heartbeat",
                priority=P1,
            )
            analysis = result.get("response", "NONE").strip()

            if analysis != "NONE":
                anomaly_found = analysis
                logger.warning("keeper.anomaly_detected", agent_id=req.agent_id, anomaly=anomaly_found)
        except Exception as exc:
            logger.error("keeper.anomaly_scan_failed", error=str(exc))

    if anomaly_found:
        logger.warning("keeper.agent_anomaly", agent_id=req.agent_id, anomaly=anomaly_found)

    logger.info("keeper.heartbeat", agent_id=req.agent_id, status=req.status)
    return {
        "status": "ok",
        "agent_id": req.agent_id,
        "validated": True,
        "anomaly": anomaly_found
    }


@app.post("/heartbeat/validate")
async def heartbeat_validate(req: HeartbeatValidateRequest, auth: dict = Depends(require_internal_auth)):
    # Run LLM-based anomaly detection
    start = time.monotonic()
    try:
        # Fetch recent activity for context
        from .db import get_recent_memories_with_dates
        memories = await get_recent_memories_with_dates(req.agent_id, limit=20)
        compressed_log = _compress_activity_log(memories)

        prompt = get_prompts()["keeper"]["heartbeat_validate"].format(
            agent_id=req.agent_id,
            heartbeat_at=req.heartbeat_at,
            consecutive_idle_beats=req.consecutive_idle_beats,
            current_task_id=req.current_task_id or "None",
            compressed_log=compressed_log,
        )

        result = await _generate_with_ollama(
            prompt,
            model=get_gen_model(),
            agent_id=req.agent_id,
            endpoint="heartbeat/validate",
            timeout=180.0,
            format="json",
            priority=P1,
        )
        resp_text = result.get("response", "{\"is_valid\": true}").strip()

        block = _extract_json_block(resp_text)
        if block:
            verdict = json.loads(block)
            # Post-process: the 1.7B model hallucinates many benign states as anomalies.
            # We only trust anomalies that describe a crash, fatal error, or infinite loop.
            anomaly = (verdict.get("anomaly") or "").lower()
            if anomaly:
                trusted_patterns = [
                    "crash", "fatal", "infinite loop", "infinite",
                    "stuck", "repeated error", "repeated failure",
                    "retrying the same", "endless loop", "frozen",
                ]
                if not any(tp in anomaly for tp in trusted_patterns):
                    logger.info(
                        "keeper.heartbeat_false_positive_filtered",
                        agent_id=req.agent_id,
                        original_anomaly=verdict.get("anomaly"),
                    )
                    verdict = {"is_valid": True, "anomaly": None}
        else:
            verdict = {"is_valid": True}

        latency = (time.monotonic() - start) * 1000
        metrics = get_metrics()
        metrics.record_inference(
            agent_id=req.agent_id,
            endpoint="heartbeat/validate",
            model=get_gen_model(),
            latency_ms=latency,
            prompt=prompt,
            completion=json.dumps(verdict),
            status="success",
        )
        return verdict
    except Exception as exc:
        latency = (time.monotonic() - start) * 1000
        if isinstance(exc, httpx.TimeoutException):
            logger.warning(
                "heartbeat_validate timed out, failing open (is_valid=True)",
                agent_id=req.agent_id
            )
        else:
            logger.error(
                "keeper.heartbeat_validate_failed",
                error=str(exc),
                agent_id=req.agent_id
            )
        metrics = get_metrics()
        metrics.record_inference(
            agent_id=req.agent_id,
            endpoint="heartbeat/validate",
            model=get_gen_model(),
            latency_ms=latency,
            prompt=locals().get("prompt", req.heartbeat_at),
            status="error",
            error=f"{type(exc).__name__}: {str(exc)[:200]}",
        )
        return {"is_valid": True, "note": "Validation failed, failing open"}


@app.post("/pii/scrub")
async def pii_scrub(
    req: ScrubRequest,
    request: Request,
    auth: dict = Depends(require_internal_auth),
):
    agent_id = req.agent_id or request.headers.get("X-Agent-ID")
    # 1. Regex Pass: Fast, guaranteed masking of standard patterns
    text = req.text
    mapping = {}

    # We'll use a subset of patterns for local substitution
    regex_patterns = {
        "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "phone": r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    }

    counter = 1
    for pii_type, pattern in regex_patterns.items():
        import re
        matches = list(set(re.findall(pattern, text)))
        for match in matches:
            placeholder = f"[[PII_{pii_type.upper()}_{counter}]]"
            mapping[placeholder] = match
            text = text.replace(match, placeholder)
            counter += 1

    # 2. LLM Pass: Context-aware scrubbing for names, IDs, etc.
    prompt = get_prompts()["keeper"]["pii_scrub"].format(text=text)

    try:
        result = await _generate_with_ollama(
            prompt,
            model=get_gen_model(),
            agent_id=agent_id,
            endpoint="pii/scrub",
            priority=P1,
        )
        resp_text = result.get("response", "")
        block = _extract_json_block(resp_text)
        if block:
            try:
                llm_data = json.loads(block)
                # Merge LLM results with Regex results
                text = llm_data.get("scrubbed_text", text)
                mapping.update(llm_data.get("mapping", {}))
            except Exception:
                logger.warning("keeper.pii_scrub.llm_json_parse_failed", raw_resp=resp_text)

        return {"scrubbed_text": text, "mapping": mapping}
    except Exception as exc:
        logger.error("keeper.pii_scrub_failed", error=str(exc))
        # Fail-Safe: Return regex-scrubbed version if LLM fails
        return {"scrubbed_text": text, "mapping": mapping, "note": "LLM pass failed, only regex pass applied"}


from .session_prep import session_prep, rehydrate as session_rehydrate
from .pii_models import SessionPrepRequest, RehydrateRequest

@app.post("/session-prep")
async def session_prep_endpoint(
    req: SessionPrepRequest,
    auth: dict = Depends(require_internal_auth),
):
    """Unified context injection + PII anonymization."""
    return await session_prep(req)


@app.post("/session-prep/rehydrate")
async def session_prep_rehydrate(
    req: RehydrateRequest,
    auth: dict = Depends(require_internal_auth),
):
    """Re-hydrate tokens back to original values."""
    return await session_rehydrate(req)


@app.post("/pii/unscrub")
async def pii_unscrub(
    req: UnscrubRequest,
    request: Request,
    auth: dict = Depends(require_internal_auth),
):
    agent_id = req.agent_id or request.headers.get("X-Agent-ID")
    metrics = get_metrics()
    metrics.start_request()
    start = time.monotonic()

    text = req.text
    for placeholder, original in req.mapping.items():
        text = text.replace(placeholder, original)

    latency = (time.monotonic() - start) * 1000
    metrics.record_inference(
        agent_id=agent_id,
        endpoint="pii/unscrub",
        model=None,
        latency_ms=latency,
        prompt=req.text,
        completion=text,
        status="success",
    )
    return {"text": text}


@app.post("/skill/clean")
async def skill_clean(
    req: CleanRequest,
    request: Request,
    auth: dict = Depends(require_internal_auth),
):
    agent_id = req.agent_id or request.headers.get("X-Agent-ID")
    MAX_CLEAN_CHARS = 20000
    raw_data = req.raw_data
    warning = ""

    if len(raw_data) > MAX_CLEAN_CHARS:
        warning = (
            f"[WARNING: Raw data truncated from {len(raw_data)} "
            f"to {MAX_CLEAN_CHARS} chars before cleaning]\n\n"
        )
        raw_data = raw_data[:MAX_CLEAN_CHARS]

    prompt = get_prompts()["keeper"]["skill_clean"].format(
        extraction_goal=req.extraction_goal, raw_data=raw_data
    )
    try:
        result = await _generate_with_ollama(
            prompt, model=get_gen_model(), agent_id=agent_id, endpoint="skill/clean"
        )
        cleaned = result.get("response", "")
        return {"cleaned_data": f"{warning}{cleaned}", "model": get_gen_model()}
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        logger.error("keeper.skill_clean_failed", error=str(exc))
        raise HTTPException(status_code=503, detail="Keeper LLM unavailable: Ollama unreachable")
    except Exception as exc:
        logger.error("keeper.skill_clean_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/verify/logic")
async def verify_logic(
    req: VerifyLogicRequest,
    request: Request,
    auth: dict = Depends(require_internal_auth),
):
    agent_id = req.agent_id or request.headers.get("X-Agent-ID")
    prompt = get_prompts()["keeper"]["verify_logic"].format(
        context=req.context or "None", text=req.text
    )
    try:
        result = await _generate_with_ollama(
            prompt, model=get_gen_model(), agent_id=agent_id, endpoint="verify/logic"
        )
        resp_text = result.get("response", "")
        block = _extract_json_block(resp_text)
        if block:
            return json.loads(block)
        return {"is_valid": True, "reason": "Failed to parse judge JSON"}
    except Exception as exc:
        logger.error("keeper.verify_logic_failed", error=str(exc))
        return {"is_valid": True, "reason": f"Judge error: {exc}"}


@app.get("/dashboard")
async def dashboard(auth: dict = Depends(require_internal_auth)):
    metrics = get_metrics()
    queue_depths = priority_manager.get_depths()
    snapshot = metrics.get_snapshot(queue_depths=queue_depths)
    settings = get_settings()

    # Probe Ollama for running models + VRAM
    ollama_ps = {}
    ollama_status = "unknown"
    try:
        async with OllamaClient().session() as client:
            ollama_ps = await client.ps()
        ollama_status = "ok"
    except Exception as exc:
        logger.warning("keeper.dashboard_ollama_ps_failed", error=str(exc))
        ollama_status = "fail"

    # Probe Ollama for default model details
    model_info = {}
    try:
        async with OllamaClient().session() as client:
            model_info = await client.show_model(get_gen_model())
    except Exception as exc:
        logger.warning("keeper.dashboard_model_info_failed", error=str(exc))

    uptime_seconds = round(time.monotonic() - metrics._start_time, 2)

    return {
        "identity": {
            "backend": "ollama",
            "ollama_host": settings.ollama_host or "http://localhost:11434",
            "default_gen_model": model_manager.get_model("gen"),
            "default_embed_model": model_manager.get_model("embed"),
            "model_info": {
                "parameter_size": model_info.get("details", {}).get("parameter_size"),
                "quantization": model_info.get("details", {}).get("quantization_level"),
                "context_length": model_info.get("model_info", {}).get("context_length"),
                "format": model_info.get("details", {}).get("format"),
            },
        },
        "health": {
            "status": "ready" if ollama_status == "ok" else "degraded",
            "uptime_seconds": uptime_seconds,
            "active_requests": snapshot["active_requests"],
            "ollama_ps": ollama_ps,
        },
        "stats": {
            "total_requests": snapshot["total_requests"],
            "avg_latency_ms": snapshot["avg_latency_ms"],
            "agent_calls": snapshot["agent_calls"],
            "error_counts": snapshot["error_counts"],
        },
        "recent_inferences": snapshot["recent_inferences"],
        "config": {
            "num_ctx": model_manager.config.get("num_ctx", 4096),
            "num_batch": model_manager.config.get("num_batch", 512),
            "ollama_gen_model": model_manager.get_model("gen"),
            "ollama_embed_model": model_manager.get_model("embed"),
        },
    }
