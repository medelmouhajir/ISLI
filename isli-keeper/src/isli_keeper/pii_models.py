"""Pydantic models for the unified session-prep / PII mesh endpoints."""

from typing import Any
from pydantic import BaseModel


class SessionPrepRequest(BaseModel):
    session_id: str
    agent_id: str
    messages: list[dict[str, Any]] = []
    context_summary: str = ""
    mode: str = "full"  # "full" = context + PII | "pii_only" = just anonymize
    use_slm: bool = True
    memory_similarity_threshold: float = 0.4
    agent_config: dict[str, Any] | None = None
    available_skills: list[dict[str, str]] = []  # [{"name": "...", "hint": "..."}]


class SessionPrepResponse(BaseModel):
    original_context_summary: str = ""
    scrubbed_context_summary: str = ""
    scrubbed_messages: list[dict[str, Any]] = []
    token_map: dict[str, str] = {}
    categories_found: list[str] = []
    cache_hit: bool = False
    relevant_skills: list[str] = []


class RehydrateRequest(BaseModel):
    text: str
    session_id: str
    agent_id: str | None = None


class RehydrateResponse(BaseModel):
    original_text: str
    unresolved_tokens: list[str] = []
