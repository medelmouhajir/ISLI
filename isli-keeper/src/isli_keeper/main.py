import json
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx
import structlog
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel

from .auth import require_internal_auth
from .config import get_settings
from .db import close_db, get_recent_memories, get_relevant_memories, init_db
from .metrics import get_metrics
from .ollama_client import OllamaClient
from .telemetry import get_trace_id, instrument_fastapi

SERVICE_NAME = "isli-keeper"

logger = structlog.get_logger()

settings = get_settings()
DEFAULT_EMBED_MODEL = settings.ollama_embed_model
DEFAULT_GEN_MODEL = settings.ollama_gen_model


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


def _compress_activity_log(entries: list[str], max_entries: int = 20, max_chars: int = 2000) -> str:
    # Deduplicate consecutive identical entries
    deduped = []
    prev = None
    count = 1
    for entry in entries:
        if entry == prev:
            count += 1
        else:
            if prev is not None:
                suffix = f" (repeated {count}x)" if count > 1 else ""
                deduped.append(f"{prev}{suffix}")
            prev = entry
            count = 1
    if prev:
        suffix = f" (repeated {count}x)" if count > 1 else ""
        deduped.append(f"{prev}{suffix}")
    
    # Take last N unique entries
    recent = deduped[-max_entries:]
    
    # Hard cap on total characters
    result = "\n".join(recent)
    return result[-max_chars:] if len(result) > max_chars else result


async def _generate_with_ollama(
    prompt: str,
    model: str,
    agent_id: str | None = None,
    endpoint: str = "generate",
    timeout: float | None = None,
) -> dict:
    metrics = get_metrics()
    metrics.start_request()
    start = time.monotonic()
    try:
        async with OllamaClient().session() as client:
            result = await client.generate(model, prompt, timeout=timeout)
        latency = (time.monotonic() - start) * 1000
        metrics.record_inference(
            agent_id=agent_id,
            endpoint=endpoint,
            model=model,
            latency_ms=latency,
            prompt=prompt,
            completion=result.get("response", ""),
            tokens_in=len(prompt) // 4,
            tokens_out=len(result.get("response", "")) // 4,
            status="success",
        )
        return result
    except Exception as exc:
        latency = (time.monotonic() - start) * 1000
        metrics.record_inference(
            agent_id=agent_id,
            endpoint=endpoint,
            model=model,
            latency_ms=latency,
            prompt=prompt,
            status="error",
            error=str(exc),
        )
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("keeper.startup", service=SERVICE_NAME)
    await init_db()
    yield
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
    model: str = DEFAULT_EMBED_MODEL
    agent_id: str | None = None


class SummarizeRequest(BaseModel):
    text: str
    max_length: int = 256
    agent_id: str | None = None


class GenerateRequest(BaseModel):
    prompt: str
    model: str = DEFAULT_GEN_MODEL
    options: dict[str, Any] | None = None
    agent_id: str | None = None


class ContextInjectRequest(BaseModel):
    agent_id: str
    session_id: str | None = None
    task_description: str | None = None
    agent_name: str | None = None
    agent_description: str | None = None
    agent_persona: str | None = None
    memory_similarity_threshold: float = 0.4


class HeartbeatRequest(BaseModel):
    agent_id: str
    status: str
    anomaly: str | None = None


class HeartbeatValidateRequest(BaseModel):
    agent_id: str
    heartbeat_at: str


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
    _auth: dict = Depends(require_internal_auth),
):
    agent_id = req.agent_id or request.headers.get("X-Agent-ID")
    metrics = get_metrics()
    metrics.start_request()
    start = time.monotonic()
    try:
        async with OllamaClient().session() as client:
            embedding = await client.embed(req.model, req.input)
        latency = (time.monotonic() - start) * 1000
        metrics.record_inference(
            agent_id=agent_id,
            endpoint="embed",
            model=req.model,
            latency_ms=latency,
            prompt=req.input,
            status="success",
        )
        return {"embedding": embedding, "model": req.model}
    except Exception as exc:
        latency = (time.monotonic() - start) * 1000
        metrics.record_inference(
            agent_id=agent_id,
            endpoint="embed",
            model=req.model,
            latency_ms=latency,
            prompt=req.input,
            status="error",
            error=str(exc),
        )
        logger.error("keeper.embed_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/summarize")
async def summarize(
    req: SummarizeRequest,
    request: Request,
    _auth: dict = Depends(require_internal_auth),
):
    agent_id = req.agent_id or request.headers.get("X-Agent-ID")
    prompt = (
        f"Summarize the following text in under {req.max_length} words:\n\n"
        f"{req.text}\n\nSummary:"
    )
    try:
        result = await _generate_with_ollama(
            prompt, model=DEFAULT_GEN_MODEL, agent_id=agent_id, endpoint="summarize"
        )
        summary = result.get("response", "")
        return {"summary": summary, "model": DEFAULT_GEN_MODEL}
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
    _auth: dict = Depends(require_internal_auth),
):
    agent_id = req.agent_id or request.headers.get("X-Agent-ID")
    prompt = (
        "Update the structured session journal based on the recent messages. "
        "Maintain the following format precisely:\n\n"
        "[Context]\n(General environment, active versions, user preferences)\n"
        "[Decisions]\n(Key decisions made, agreed-upon constraints, or changes in direction)\n"
        "[Last State]\n(What the agent was doing most recently and where it left off)\n\n"
        f"Old Journal:\n{req.old_journal or 'No previous journal.'}\n\n"
        "Recent Messages:\n"
    )
    for msg in req.recent_messages:
        prompt += f"{msg.get('role', 'user')}: {msg.get('content', '')}\n"

    prompt += "\nUpdated Structured Journal:"

    try:
        result = await _generate_with_ollama(
            prompt, model=DEFAULT_GEN_MODEL, agent_id=agent_id, endpoint="journal/update"
        )
        updated_journal = result.get("response", "")
        return {"journal": updated_journal, "model": DEFAULT_GEN_MODEL}
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        logger.error("keeper.journal_update_failed", error=str(exc))
        raise HTTPException(status_code=503, detail="Keeper LLM unavailable: Ollama unreachable")
    except Exception as exc:
        logger.error("keeper.journal_update_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/context/inject")
async def context_inject(req: ContextInjectRequest, _auth: dict = Depends(require_internal_auth)):
    try:
        # 1. Fetch episodic memories (Tier 2) - use semantic search if task description is provided
        memories = []
        if req.task_description:
            metrics = get_metrics()
            metrics.start_request()
            embed_start = time.monotonic()
            try:
                async with OllamaClient().session() as client:
                    embedding = await client.embed(DEFAULT_EMBED_MODEL, req.task_description)
                embed_latency = (time.monotonic() - embed_start) * 1000
                metrics.record_inference(
                    agent_id=req.agent_id,
                    endpoint="embed",
                    model=DEFAULT_EMBED_MODEL,
                    latency_ms=embed_latency,
                    prompt=req.task_description,
                    status="success",
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
                embed_latency = (time.monotonic() - embed_start) * 1000
                metrics.record_inference(
                    agent_id=req.agent_id,
                    endpoint="embed",
                    model=DEFAULT_EMBED_MODEL,
                    latency_ms=embed_latency,
                    prompt=req.task_description,
                    status="error",
                    error=str(exc),
                )
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
        if req.agent_persona:
            identity_parts.append(f"Persona: {req.agent_persona}")

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

        if not context_parts:
            return {
                "context_summary": "No previous context found.",
                "relevant_memories": [],
                "model": "fast-path"
            }

        context_summary = "\n\n".join(context_parts)

        return {
            "context_summary": context_summary,
            "relevant_memories": memories,
            "model": "fast-path"
        }
    except Exception as exc:
        logger.error("keeper.context_inject_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/generate")
async def generate(
    req: GenerateRequest,
    request: Request,
    _auth: dict = Depends(require_internal_auth),
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


@app.get("/models")
async def list_models(_auth: dict = Depends(require_internal_auth)):
    try:
        async with OllamaClient().session() as client:
            models = await client.list_models()
        return {"models": models}
    except Exception as exc:
        logger.error("keeper.list_models_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/heartbeat")
async def heartbeat(req: HeartbeatRequest, _auth: dict = Depends(require_internal_auth)):
    anomaly_found = req.anomaly

    # Run LLM-based anomaly detection if status is unusual or requested
    if not anomaly_found and req.status not in ("online", "idle"):
        try:
            # Fetch recent activity for context
            from .db import get_recent_memories
            memories = await get_recent_memories(req.agent_id, limit=3)
            activity_text = "\n".join(memories)

            prompt = (
                f"Analyze the following recent activity for agent '{req.agent_id}' (Status: {req.status}). "
                "Detect any anomalies like infinite loops, stuck states, or repetitive behavior.\n\n"
                f"Activity:\n{activity_text}\n\n"
                "If an anomaly is found, describe it in one short sentence. Otherwise, respond with 'NONE'."
            )

            result = await _generate_with_ollama(prompt, model=DEFAULT_GEN_MODEL, agent_id=req.agent_id, endpoint="heartbeat")
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
async def heartbeat_validate(req: HeartbeatValidateRequest, _auth: dict = Depends(require_internal_auth)):
    # Run LLM-based anomaly detection
    try:
        # Fetch recent activity for context
        from .db import get_recent_memories
        memories = await get_recent_memories(req.agent_id, limit=20)
        compressed_log = _compress_activity_log(memories)

        prompt = (
            f"Analyze the recent activity for agent '{req.agent_id}'. "
            f"Heartbeat received at: {req.heartbeat_at}\n\n"
            "Detect any anomalies like infinite loops, stuck states, or repetitive behavior.\n"
            "Activity Log:\n"
            f"{compressed_log}\n\n"
            "If an anomaly is found, respond with JSON: {\"is_valid\": false, \"anomaly\": \"...\"}. "
            "Otherwise, respond with JSON: {\"is_valid\": true}"
        )

        result = await _generate_with_ollama(
            prompt,
            model=DEFAULT_GEN_MODEL,
            agent_id=req.agent_id,
            endpoint="heartbeat/validate",
            timeout=30.0
        )
        resp_text = result.get("response", "{\"is_valid\": true}").strip()

        block = _extract_json_block(resp_text)
        if block:
            return json.loads(block)
        return {"is_valid": True}
    except Exception as exc:
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
        return {"is_valid": True, "note": "Validation failed, failing open"}


@app.post("/pii/scrub")
async def pii_scrub(
    req: ScrubRequest,
    request: Request,
    _auth: dict = Depends(require_internal_auth),
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
    prompt = (
        "Identify any REMAINING Personal Identifiable Information (PII) in the following text. "
        "PII includes names, proprietary IDs, and addresses. Do NOT re-scrub placeholders starting with [[PII_.\n\n"
        "Replace remaining PII with a unique placeholder like [[PII_NAME_N]] or [[PII_ADDR_N]].\n\n"
        f"Text: {text}\n\n"
        "Return ONLY a JSON object with two fields: 'scrubbed_text' and 'mapping' (new placeholder -> original value)."
    )

    try:
        result = await _generate_with_ollama(prompt, model=DEFAULT_GEN_MODEL, agent_id=agent_id, endpoint="pii/scrub")
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


@app.post("/pii/unscrub")
async def pii_unscrub(
    req: UnscrubRequest,
    request: Request,
    _auth: dict = Depends(require_internal_auth),
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
    _auth: dict = Depends(require_internal_auth),
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

    prompt = (
        f"Clean the following raw data and extract only information relevant to: "
        f"{req.extraction_goal}\n\n"
        "If the data is HTML, strip all tags and boilerplate. "
        "Return a clean, compact JSON or text summary.\n\n"
        f"Raw Data:\n{raw_data}\n\n"
        "Cleaned Data:"
    )
    try:
        result = await _generate_with_ollama(
            prompt, model=DEFAULT_GEN_MODEL, agent_id=agent_id, endpoint="skill/clean"
        )
        cleaned = result.get("response", "")
        return {"cleaned_data": f"{warning}{cleaned}", "model": DEFAULT_GEN_MODEL}
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
    _auth: dict = Depends(require_internal_auth),
):
    agent_id = req.agent_id or request.headers.get("X-Agent-ID")
    prompt = (
        "Act as a logic judge. Analyze the following agent output for contradictions, "
        "infinite reasoning loops, or safety violations.\n\n"
        f"Context: {req.context or 'None'}\n"
        f"Agent Output: {req.text}\n\n"
        "Is this output valid? Respond with JSON: {\"is_valid\": bool, \"reason\": \"string\"}"
    )
    try:
        result = await _generate_with_ollama(
            prompt, model=DEFAULT_GEN_MODEL, agent_id=agent_id, endpoint="verify/logic"
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
async def dashboard(_auth: dict = Depends(require_internal_auth)):
    metrics = get_metrics()
    snapshot = metrics.get_snapshot()
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
            model_info = await client.show_model(DEFAULT_GEN_MODEL)
    except Exception as exc:
        logger.warning("keeper.dashboard_model_info_failed", error=str(exc))

    uptime_seconds = round(time.monotonic() - metrics._start_time, 2)

    return {
        "identity": {
            "backend": "ollama",
            "ollama_host": settings.ollama_host or "http://localhost:11434",
            "default_gen_model": DEFAULT_GEN_MODEL,
            "default_embed_model": DEFAULT_EMBED_MODEL,
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
            "num_ctx": 4096,
            "num_batch": 512,
            "ollama_gen_model": DEFAULT_GEN_MODEL,
            "ollama_embed_model": DEFAULT_EMBED_MODEL,
        },
    }
