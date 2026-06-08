from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field

class AgentConfig(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    persona: Optional[str] = None
    model_provider: Optional[str] = None
    model_id: Optional[str] = None
    channels: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    known_agent_ids: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    token_budget: Optional[int] = None
    turn_token_cap: Optional[int] = None
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    heartbeat_interval: int = 180
    model_routing_enabled: bool = False
    secondary_models: list[dict] = Field(default_factory=list)
    # Forward-compatible fields from Core Agent record (may be absent in config endpoint)
    status: Optional[str] = None
    status_reason: Optional[str] = None

class Task(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    status: str
    priority: int = 3
    tags: list[str] = Field(default_factory=list)
    input: str
    session_id: Optional[str] = None
    agent_id: Optional[str] = None
    created_at: Optional[datetime] = None
    context_summary: Optional[str] = None
    payload: Optional[dict[str, Any]] = None
    scheduled_at: Optional[datetime] = None
    cron_expression: Optional[str] = None
    complexity_score: Optional[int] = None
    complexity_tier: Optional[str] = None
    routed_model_provider: Optional[str] = None
    routed_model_id: Optional[str] = None
    routed_model_reason: Optional[str] = None

class ContextInjection(BaseModel):
    context_summary: str
    relevant_memories: list[str] = Field(default_factory=list)

class Checkpoint(BaseModel):
    task_id: str
    turn_number: int
    messages: list[dict[str, Any]]
    tool_calls: Optional[list[dict[str, Any]]] = None
