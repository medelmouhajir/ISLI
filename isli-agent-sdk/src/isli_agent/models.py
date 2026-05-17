from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field

class AgentConfig(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    model_provider: str
    model_id: str
    channels: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    token_budget: Optional[int] = None
    heartbeat_interval: int = 30

class Task(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    status: str
    input: str
    session_id: Optional[str] = None
    agent_id: Optional[str] = None
    context_summary: Optional[str] = None
    payload: Optional[dict[str, Any]] = None

class ContextInjection(BaseModel):
    context_summary: str
    relevant_memories: list[str] = Field(default_factory=list)

class Checkpoint(BaseModel):
    task_id: str
    turn_number: int
    messages: list[dict[str, Any]]
    tool_calls: Optional[list[dict[str, Any]]] = None
