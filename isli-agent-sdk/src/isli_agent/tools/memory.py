from typing import Any

from isli_agent.client import CoreClient


async def memory_save(
    agent_id: str,
    content: str,
    core_client: CoreClient,
    metadata: dict[str, Any] | None = None,
    embedding: list[float] | None = None,
) -> dict[str, Any]:
    """Save a fact to the agent's Tier 3 semantic memory."""
    payload: dict[str, Any] = {"agent_id": agent_id, "content": content}
    if metadata is not None:
        payload["metadata"] = metadata
    if embedding is not None:
        payload["embedding"] = embedding
    resp = await core_client.client.post(
        "/v1/skills/memory-save/save",
        json=payload,
        headers=core_client._get_headers(),
    )
    resp.raise_for_status()
    return resp.json()


async def memory_delete(agent_id: str, fact_id: str, core_client: CoreClient) -> dict[str, Any]:
    """Delete a fact from the agent's Tier 3 semantic memory."""
    resp = await core_client.client.post(
        "/v1/skills/memory-delete/delete",
        json={"agent_id": agent_id, "fact_id": fact_id},
        headers=core_client._get_headers(),
    )
    resp.raise_for_status()
    return resp.json()


async def memory_search(
    agent_id: str,
    query_text: str,
    core_client: CoreClient,
    limit: int = 5,
) -> dict[str, Any]:
    """Search the agent's Tier 3 semantic memory for relevant facts."""
    resp = await core_client.client.post(
        "/v1/skills/memory-search/search",
        json={"agent_id": agent_id, "query_text": query_text, "limit": limit},
        headers=core_client._get_headers(),
    )
    resp.raise_for_status()
    return resp.json()


MEMORY_SAVE_DEF = {
    "type": "function",
    "function": {
        "name": "memory_save",
        "description": "Save a fact to the agent's long-term semantic memory. Use this to remember important information for later retrieval.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The fact or information to save",
                },
                "metadata": {
                    "type": "object",
                    "description": "Optional metadata dict (e.g. tags, source)",
                },
                "embedding": {
                    "type": "array",
                    "description": "Optional pre-computed embedding vector",
                    "items": {"type": "number"},
                },
            },
            "required": ["content"],
        },
    },
}

MEMORY_DELETE_DEF = {
    "type": "function",
    "function": {
        "name": "memory_delete",
        "description": "Delete a previously saved fact from the agent's semantic memory by its fact ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "fact_id": {
                    "type": "string",
                    "description": "The unique ID of the fact to delete",
                },
            },
            "required": ["fact_id"],
        },
    },
}

MEMORY_SEARCH_DEF = {
    "type": "function",
    "function": {
        "name": "memory_search",
        "description": "Search the agent's semantic memory for facts relevant to a query.",
        "parameters": {
            "type": "object",
            "properties": {
                "query_text": {
                    "type": "string",
                    "description": "The query text to search for",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                    "default": 5,
                },
            },
            "required": ["query_text"],
        },
    },
}
