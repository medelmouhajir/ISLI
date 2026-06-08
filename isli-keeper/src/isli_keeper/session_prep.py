"""Unified session-prep endpoint — context injection + PII anonymization in one pass."""

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from typing import Any

import structlog

from .db import _pool
from .pii_models import SessionPrepRequest, SessionPrepResponse, RehydrateRequest, RehydrateResponse
from .pii_prompts import SESSION_PREP_PROMPT, PII_ONLY_PROMPT
from .pii_vault import (
    mint_token,
    regex_scan,
    apply_tokens,
    rehydrate_text,
    PiiVault,
)
from .ollama_client import OllamaClient
from .prompts_loader import get_prompts
from .metrics import get_metrics
from .config import get_settings

logger = structlog.get_logger()

# In-memory exact-match cache: sha256(request_json) -> (response_dict, expires_at)
_PREP_CACHE: dict[str, tuple[dict, float]] = {}
_CACHE_TTL_SECONDS = 3600.0

# In-memory token vault (hot cache) — maps session_id -> token_map
_SESSION_TOKEN_CACHE: dict[str, dict[str, str]] = {}


def _cache_key(request: SessionPrepRequest) -> str:
    """Build a deterministic cache key from the request."""
    payload = {
        "session_id": request.session_id,
        "messages": request.messages,
        "context_summary": request.context_summary,
        "mode": request.mode,
        "use_slm": request.use_slm,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _get_cached(request: SessionPrepRequest) -> dict | None:
    key = _cache_key(request)
    now = time.monotonic()
    entry = _PREP_CACHE.get(key)
    if entry and entry[1] > now:
        return {**entry[0], "cache_hit": True}
    return None


def _set_cached(request: SessionPrepRequest, response: dict) -> None:
    key = _cache_key(request)
    _PREP_CACHE[key] = (response, time.monotonic() + _CACHE_TTL_SECONDS)


def _assemble_combined_text(request: SessionPrepRequest) -> str:
    """Concatenate all text the SLM needs to analyze."""
    parts: list[str] = []
    if request.context_summary:
        parts.append(f"Previous context:\n{request.context_summary}")
    for msg in request.messages[-10:]:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        parts.append(f"{role}: {content}")
    return "\n\n".join(parts)


async def _generate_with_ollama(prompt: str, model: str, agent_id: str | None, endpoint: str) -> dict:
    """Thin wrapper around OllamaClient.generate()."""
    from .main import _generate_with_ollama as _gen
    return await _gen(prompt, model=model, agent_id=agent_id, endpoint=endpoint)


def _extract_json_block(text: str) -> str | None:
    """Extract a JSON block from markdown-style code fences or raw text."""
    # Try fenced code block first
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if m:
        return m.group(1)
    # Try raw JSON object
    m = re.search(r"(\{.*\})", text, re.DOTALL)
    if m:
        return m.group(1)
    return None


def _build_unified_prompt(combined_text: str, agent_config: dict[str, Any] | None) -> str:
    """Assemble the SLM prompt for dual context+PII output."""
    persona = (agent_config or {}).get("persona", "")
    persona_hint = f"\nAgent persona: {persona}" if persona else ""
    return SESSION_PREP_PROMPT.format(text=combined_text + persona_hint)


def _build_pii_only_prompt(combined_text: str) -> str:
    return PII_ONLY_PROMPT.format(text=combined_text)


def _parse_dual_output(raw_output: str) -> tuple[str, list[dict[str, str]]]:
    """Parse context_summary and entities from SLM JSON output."""
    block = _extract_json_block(raw_output)
    if not block:
        logger.warning("session_prep.no_json_block", raw=raw_output[:200])
        return raw_output, []
    try:
        data = json.loads(block)
        if isinstance(data, list):
            # LLM returned just the entities array
            return "", data
        summary = data.get("context_summary", "")
        entities = data.get("entities", [])
        if not isinstance(entities, list):
            entities = []
        return summary, entities
    except json.JSONDecodeError:
        logger.warning("session_prep.json_parse_failed", raw=raw_output[:200])
        return raw_output, []


async def _persist_tokens_to_db(session_id: str, token_map: dict[str, str]) -> None:
    """Persist token mappings to PostgreSQL for durability."""
    global _pool
    if not _pool:
        return
    from .compliance.encryption import PIIEncryption
    enc = PIIEncryption()
    now = datetime.now(timezone.utc)
    async with _pool.acquire() as conn:
        for token, original in token_map.items():
            parts = token.strip("{}").split(":")
            category = parts[1] if len(parts) >= 2 else "unknown"
            encrypted = enc.encrypt_field(original, context=session_id)
            await conn.execute(
                """
                INSERT INTO pii_token_map (session_id, token_id, category, encrypted_value, created_at)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (session_id, token_id) DO UPDATE SET
                    encrypted_value = EXCLUDED.encrypted_value,
                    created_at = EXCLUDED.created_at
                """,
                session_id, token, category, encrypted, now,
            )


async def _load_tokens_from_db(session_id: str) -> dict[str, str]:
    """Load token mappings from PostgreSQL."""
    global _pool
    if not _pool:
        return {}
    from .compliance.encryption import PIIEncryption
    enc = PIIEncryption()
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT token_id, encrypted_value FROM pii_token_map WHERE session_id = $1",
            session_id,
        )
    result: dict[str, str] = {}
    for row in rows:
        try:
            original = enc.decrypt_field(row["encrypted_value"])
            result[row["token_id"]] = original
        except Exception:
            continue
    return result


async def _ensure_pii_token_map_table() -> None:
    """Create the pii_token_map table if it doesn't exist."""
    global _pool
    if not _pool:
        return
    async with _pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pii_token_map (
                session_id TEXT NOT NULL,
                token_id TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'unknown',
                encrypted_value TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (session_id, token_id)
            )
            """
        )


async def session_prep(request: SessionPrepRequest) -> SessionPrepResponse:
    """Unified context injection + PII anonymization."""
    metrics = get_metrics()
    metrics.start_request()
    start = time.monotonic()

    # ── Tier 0: Exact-match cache ──
    cached = _get_cached(request)
    if cached:
        logger.info("session_prep.cache_hit", session_id=request.session_id)
        return SessionPrepResponse(**cached)

    # ── Assemble combined text ──
    combined_text = _assemble_combined_text(request)

    # ── Tier 1: Regex pre-filter ──
    regex_hits = regex_scan(combined_text)
    has_historical_tokens = bool(_SESSION_TOKEN_CACHE.get(request.session_id))

    if not regex_hits and not has_historical_tokens and request.mode == "pii_only":
        # Nothing to do for pure PII mode
        response = SessionPrepResponse(
            original_context_summary=request.context_summary,
            scrubbed_context_summary=request.context_summary,
            scrubbed_messages=request.messages,
            token_map={},
            categories_found=[],
            cache_hit=False,
        )
        _set_cached(request, response.model_dump())
        return response

    # ── Tier 2: SLM call (unified or PII-only) ──
    if request.use_slm:
        if request.mode == "full":
            prompt = _build_unified_prompt(combined_text, request.agent_config)
        else:
            prompt = _build_pii_only_prompt(combined_text)

        try:
            settings = get_settings()
            result = await _generate_with_ollama(
                prompt,
                model=settings.ollama_gen_model,
                agent_id=request.agent_id,
                endpoint="session-prep",
            )
            raw_output = result.get("response", "")
            context_summary, entities = _parse_dual_output(raw_output)
        except Exception as exc:
            logger.error("session_prep.slm_failed", error=str(exc))
            # Degrade to regex-only
            context_summary = combined_text if request.mode == "full" else ""
            entities = []
    else:
        # Regex-only mode
        context_summary = combined_text if request.mode == "full" else ""
        entities = []

    # ── Merge regex + SLM entities ──
    all_entities: list[dict[str, str]] = []
    seen_values: set[str] = set()
    for cat, matches in regex_hits.items():
        for match in matches:
            norm = match.lower().strip()
            if norm not in seen_values:
                seen_values.add(norm)
                all_entities.append({"type": cat, "value": match})
    for ent in entities:
        val = ent.get("value", "").strip()
        norm = val.lower()
        if norm and norm not in seen_values:
            seen_values.add(norm)
            all_entities.append(ent)

    # ── Mint deterministic tokens ──
    token_map: dict[str, str] = {}
    categories_found: set[str] = set()
    existing_map = _SESSION_TOKEN_CACHE.get(request.session_id, {})

    for entity in all_entities:
        category = entity.get("type", "unknown")
        value = entity.get("value", "")
        if not value:
            continue
        token = mint_token(request.session_id, category, value)
        token_map[token] = value
        categories_found.add(category)

    # Merge with existing session tokens
    full_map = {**existing_map, **token_map}
    _SESSION_TOKEN_CACHE[request.session_id] = full_map

    # ── Apply tokens ──
    if request.mode == "full":
        original_summary = context_summary
        scrubbed_summary = apply_tokens(original_summary, full_map)
    else:
        original_summary = request.context_summary
        scrubbed_summary = apply_tokens(original_summary, full_map)

    scrubbed_messages = []
    for msg in request.messages:
        content = msg.get("content", "")
        scrubbed_content = apply_tokens(content, full_map)
        scrubbed_messages.append({**msg, "content": scrubbed_content})

    # ── Persist to DB ──
    await _persist_tokens_to_db(request.session_id, token_map)

    response = SessionPrepResponse(
        original_context_summary=original_summary,
        scrubbed_context_summary=scrubbed_summary,
        scrubbed_messages=scrubbed_messages,
        token_map=full_map,
        categories_found=sorted(categories_found),
        cache_hit=False,
    )
    _set_cached(request, response.model_dump())

    latency = (time.monotonic() - start) * 1000
    metrics.record_inference(
        agent_id=request.agent_id,
        endpoint="session-prep",
        model=get_settings().ollama_gen_model,
        latency_ms=latency,
        prompt=combined_text[:200],
        completion=scrubbed_summary[:200],
        status="success",
    )
    return response


async def rehydrate(request: RehydrateRequest) -> RehydrateResponse:
    """Re-hydrate tokens back to original values using session cache or DB."""
    start = time.monotonic()
    session_id = request.session_id

    # Try in-memory cache first
    token_map = _SESSION_TOKEN_CACHE.get(session_id, {})
    if not token_map:
        # Fallback to DB
        token_map = await _load_tokens_from_db(session_id)
        if token_map:
            _SESSION_TOKEN_CACHE[session_id] = token_map

    original_text, unresolved = rehydrate_text(request.text, token_map)

    latency = (time.monotonic() - start) * 1000
    logger.info("session_prep.rehydrate", session_id=session_id, latency_ms=latency, unresolved=len(unresolved))
    return RehydrateResponse(original_text=original_text, unresolved_tokens=unresolved)


# Ensure table exists on import (called from main.py lifespan)
async def init_pii_vault() -> None:
    await _ensure_pii_token_map_table()
