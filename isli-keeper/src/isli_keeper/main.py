import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
import structlog

from .telemetry import instrument_fastapi, get_trace_id
from .config import get_settings
from .ollama_client import OllamaClient
from .fallback import KeeperFallback
from .db import init_db, close_db, get_recent_memories, get_relevant_memories
from .auth import require_internal_auth


SERVICE_NAME = "isli-keeper"

logger = structlog.get_logger()

DEFAULT_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
DEFAULT_GEN_MODEL = os.getenv("OLLAMA_GEN_MODEL", "qwen2.5:7b")

fallback = KeeperFallback()


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


class SummarizeRequest(BaseModel):
    text: str
    max_length: int = 256


class GenerateRequest(BaseModel):
    prompt: str
    model: str = DEFAULT_GEN_MODEL
    options: dict[str, Any] | None = None


class ContextInjectRequest(BaseModel):
    agent_id: str
    session_id: str | None = None
    task_description: str | None = None


class HeartbeatRequest(BaseModel):
    agent_id: str
    status: str
    anomaly: str | None = None


class HeartbeatValidateRequest(BaseModel):
    agent_id: str
    heartbeat_at: str


class ScrubRequest(BaseModel):
    text: str


class UnscrubRequest(BaseModel):
    text: str
    mapping: dict[str, str]


class CleanRequest(BaseModel):
    raw_data: str
    extraction_goal: str


class VerifyLogicRequest(BaseModel):
    text: str
    context: str | None = None


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

    fallback_ready = bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY"))
    return {
        "status": "ready" if ollama_ok else "degraded",
        "service": SERVICE_NAME,
        "ollama": "ok" if ollama_ok else "fail",
        "fallback_configured": fallback_ready,
    }


@app.get("/live")
async def live():
    return {"status": "alive", "service": SERVICE_NAME}


@app.post("/embed")
async def embed(req: EmbedRequest, _auth: dict = Depends(require_internal_auth)):
    try:
        async with OllamaClient().session() as client:
            embedding = await client.embed(req.model, req.input)
        return {"embedding": embedding, "model": req.model}
    except Exception as exc:
        logger.error("keeper.embed_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/summarize")
async def summarize(req: SummarizeRequest, _auth: dict = Depends(require_internal_auth)):
    prompt = f"Summarize the following text in under {req.max_length} words:\n\n{req.text}\n\nSummary:"
    try:
        result = await fallback.generate(prompt, model=DEFAULT_GEN_MODEL)
        summary = result.get("response", result.get("response", ""))
        return {"summary": summary, "model": DEFAULT_GEN_MODEL}
    except Exception as exc:
        logger.error("keeper.summarize_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))


class JournalUpdateRequest(BaseModel):
    session_id: str
    old_journal: str | None = None
    recent_messages: list[dict[str, Any]]


@app.post("/journal/update")
async def journal_update(req: JournalUpdateRequest, _auth: dict = Depends(require_internal_auth)):
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
        result = await fallback.generate(prompt, model=DEFAULT_GEN_MODEL)
        updated_journal = result.get("response", "")
        return {"journal": updated_journal, "model": DEFAULT_GEN_MODEL}
    except Exception as exc:
        logger.error("keeper.journal_update_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/context/inject")
async def context_inject(req: ContextInjectRequest, _auth: dict = Depends(require_internal_auth)):
    try:
        # 1. Fetch episodic memories (Tier 2) - use semantic search if task description is provided
        memories = []
        if req.task_description:
            try:
                async with OllamaClient().session() as client:
                    embedding = await client.embed(DEFAULT_EMBED_MODEL, req.task_description)
                memories = await get_relevant_memories(req.agent_id, embedding)
            except Exception as exc:
                logger.warning("keeper.semantic_search_failed", error=str(exc))
                memories = await get_recent_memories(req.agent_id)
        else:
            memories = await get_recent_memories(req.agent_id)
        
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
async def generate(req: GenerateRequest, _auth: dict = Depends(require_internal_auth)):
    try:
        result = await fallback.generate(req.prompt, model=req.model)
        return result
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
            
            result = await fallback.generate(prompt, model=DEFAULT_GEN_MODEL)
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
        memories = await get_recent_memories(req.agent_id, limit=5)
        activity_text = "\n".join(memories)
        
        prompt = (
            f"Analyze the recent activity for agent '{req.agent_id}'. "
            f"Heartbeat received at: {req.heartbeat_at}\n\n"
            "Detect any anomalies like infinite loops, stuck states, or repetitive behavior.\n"
            "Activity Log:\n"
            f"{activity_text}\n\n"
            "If an anomaly is found, respond with JSON: {\"is_valid\": false, \"anomaly\": \"...\"}. "
            "Otherwise, respond with JSON: {\"is_valid\": true}"
        )
        
        import json
        result = await fallback.generate(prompt, model=DEFAULT_GEN_MODEL)
        resp_text = result.get("response", "{\"is_valid\": true}").strip()
        
        if "{" in resp_text:
            return json.loads(resp_text[resp_text.find("{"):resp_text.rfind("}")+1])
        return {"is_valid": True}
    except Exception as exc:
        logger.error("keeper.heartbeat_validate_failed", error=str(exc))
        return {"is_valid": True, "note": "Validation failed, failing open"}


@app.post("/pii/scrub")
async def pii_scrub(req: ScrubRequest, _auth: dict = Depends(require_internal_auth)):
    # 1. Regex Pass: Fast, guaranteed masking of standard patterns
    from isli_core.security.content_scanner import ContentScanner
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
        import json
        result = await fallback.generate(prompt, model=DEFAULT_GEN_MODEL)
        resp_text = result.get("response", "")
        if "{" in resp_text:
            try:
                llm_data = json.loads(resp_text[resp_text.find("{"):resp_text.rfind("}")+1])
                # Merge LLM results with Regex results
                text = llm_data.get("scrubbed_text", text)
                mapping.update(llm_data.get("mapping", {}))
            except:
                logger.warning("keeper.pii_scrub.llm_json_parse_failed", raw_resp=resp_text)
        
        return {"scrubbed_text": text, "mapping": mapping}
    except Exception as exc:
        logger.error("keeper.pii_scrub_failed", error=str(exc))
        # Fail-Safe: Return regex-scrubbed version if LLM fails
        return {"scrubbed_text": text, "mapping": mapping, "note": "LLM pass failed, only regex pass applied"}


@app.post("/pii/unscrub")
async def pii_unscrub(req: UnscrubRequest, _auth: dict = Depends(require_internal_auth)):
    text = req.text
    for placeholder, original in req.mapping.items():
        text = text.replace(placeholder, original)
    return {"text": text}


@app.post("/skill/clean")
async def skill_clean(req: CleanRequest, _auth: dict = Depends(require_internal_auth)):
    MAX_CLEAN_CHARS = 20000
    raw_data = req.raw_data
    warning = ""

    if len(raw_data) > MAX_CLEAN_CHARS:
        warning = f"[WARNING: Raw data truncated from {len(raw_data)} to {MAX_CLEAN_CHARS} chars before cleaning]\n\n"
        raw_data = raw_data[:MAX_CLEAN_CHARS]

    prompt = (
        f"Clean the following raw data and extract only information relevant to: {req.extraction_goal}\n\n"
        "If the data is HTML, strip all tags and boilerplate. Return a clean, compact JSON or text summary.\n\n"
        f"Raw Data:\n{raw_data}\n\n"
        "Cleaned Data:"
    )
    try:
        result = await fallback.generate(prompt, model=DEFAULT_GEN_MODEL)
        cleaned = result.get("response", "")
        return {"cleaned_data": f"{warning}{cleaned}", "model": DEFAULT_GEN_MODEL}
    except Exception as exc:
        logger.error("keeper.skill_clean_failed", error=str(exc))
        raise HTTPException(status_code=503, detail=str(exc))



@app.post("/verify/logic")
async def verify_logic(req: VerifyLogicRequest, _auth: dict = Depends(require_internal_auth)):
    prompt = (
        "Act as a logic judge. Analyze the following agent output for contradictions, "
        "infinite reasoning loops, or safety violations.\n\n"
        f"Context: {req.context or 'None'}\n"
        f"Agent Output: {req.text}\n\n"
        "Is this output valid? Respond with JSON: {\"is_valid\": bool, \"reason\": \"string\"}"
    )
    try:
        import json
        result = await fallback.generate(prompt, model=DEFAULT_GEN_MODEL)
        resp_text = result.get("response", "")
        if "{" in resp_text:
            return json.loads(resp_text[resp_text.find("{"):resp_text.rfind("}")+1])
        return {"is_valid": True, "reason": "Failed to parse judge JSON"}
    except Exception as exc:
        logger.error("keeper.verify_logic_failed", error=str(exc))
        return {"is_valid": True, "reason": f"Judge error: {exc}"}
