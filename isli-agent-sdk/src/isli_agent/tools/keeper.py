from typing import Any

from isli_agent.client import CoreClient


def _get_tool_desc(name: str, default: str) -> str:
    try:
        from isli_agent.prompts_loader import get_prompts
        return get_prompts()["agent"]["tool_descriptions"].get(name, default)
    except Exception:
        return default


async def summarize_text(agent_id: str, text: str, core_client: CoreClient, max_length: int = 256) -> dict[str, Any]:
    """Summarize text via the Keeper skill."""
    resp = await core_client.client.post(
        "/v1/skills/summarize-text/summarize",
        json={"agent_id": agent_id, "text": text, "max_length": max_length},
        headers=core_client._get_headers(),
    )
    resp.raise_for_status()
    return resp.json()


async def embed_text(agent_id: str, input_text: str, core_client: CoreClient, model: str | None = None) -> dict[str, Any]:
    """Generate text embeddings via the Keeper skill."""
    payload: dict[str, Any] = {"agent_id": agent_id, "input": input_text}
    if model:
        payload["model"] = model
    resp = await core_client.client.post(
        "/v1/skills/embed-text/embed",
        json=payload,
        headers=core_client._get_headers(),
    )
    resp.raise_for_status()
    return resp.json()


async def summarize(agent_id: str, text: str, core_client: CoreClient, goal: str | None = None) -> dict[str, Any]:
    """Summarize text via the generic summarize skill."""
    payload = {"agent_id": agent_id, "text": text}
    if goal:
        payload["goal"] = goal
    resp = await core_client.client.post(
        "/v1/skills/summarize/summarize",
        json=payload,
        headers=core_client._get_headers(),
    )
    resp.raise_for_status()
    return resp.json()


async def translate(agent_id: str, text: str, target_lang: str, core_client: CoreClient) -> dict[str, Any]:
    """Translate text via the translate skill."""
    resp = await core_client.client.post(
        "/v1/skills/translate/translate",
        json={"agent_id": agent_id, "text": text, "target_lang": target_lang},
        headers=core_client._get_headers(),
    )
    resp.raise_for_status()
    return resp.json()


SUMMARIZE_TEXT_DEF = {
    "type": "function",
    "function": {
        "name": "summarize_text",
        "description": _get_tool_desc("summarize_text", "Summarize a long text into a shorter version using the Keeper sidecar."),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to summarize",
                },
                "max_length": {
                    "type": "integer",
                    "description": "Maximum length of the summary in characters",
                    "default": 256,
                },
            },
            "required": ["text"],
        },
    },
}

SUMMARIZE_DEF = {
    "type": "function",
    "function": {
        "name": "summarize",
        "description": _get_tool_desc("summarize", "Summarize text into a concise format, optionally with a specific goal."),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to summarize",
                },
                "goal": {
                    "type": "string",
                    "description": "Specific information to extract or focus on in the summary",
                },
            },
            "required": ["text"],
        },
    },
}

TRANSLATE_DEF = {
    "type": "function",
    "function": {
        "name": "translate",
        "description": _get_tool_desc("translate", "Translate text from one language to another."),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to translate",
                },
                "target_lang": {
                    "type": "string",
                    "description": "The target language (e.g., 'Spanish', 'French', 'Chinese')",
                },
            },
            "required": ["text", "target_lang"],
        },
    },
}

EMBED_TEXT_DEF = {
    "type": "function",
    "function": {
        "name": "embed_text",
        "description": _get_tool_desc("embed_text", "Generate a vector embedding for a piece of text."),
        "parameters": {
            "type": "object",
            "properties": {
                "input_text": {
                    "type": "string",
                    "description": "The text to embed",
                },
                "model": {
                    "type": "string",
                    "description": "Optional embedding model name",
                },
            },
            "required": ["input_text"],
        },
    },
}
