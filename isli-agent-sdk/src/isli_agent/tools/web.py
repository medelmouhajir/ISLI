from typing import Any
from isli_agent.client import CoreClient

async def web_fetch(agent_id: str, url: str, core_client: CoreClient) -> dict[str, Any]:
    """Fetch content from a URL and return structured data via the web-fetch skill."""
    resp = await core_client.client.post(
        "/v1/skills/web-fetch/fetch",
        json={"agent_id": agent_id, "url": url},
        headers=core_client._get_headers(),
    )
    resp.raise_for_status()
    return resp.json()

WEB_FETCH_DEF = {
    "type": "function",
    "function": {
        "name": "web_fetch",
        "description": "Fetch the content of a website or API from a URL.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The absolute URL to fetch",
                }
            },
            "required": ["url"],
        },
    },
}

async def web_search(agent_id: str, query: str, core_client: CoreClient, max_results: int = 5) -> dict[str, Any]:
    """Search the web for information using the web-search skill."""
    resp = await core_client.client.post(
        "/v1/skills/web-search/search",
        json={"agent_id": agent_id, "query": query, "max_results": max_results},
        headers=core_client._get_headers(),
    )
    resp.raise_for_status()
    return resp.json()

WEB_SEARCH_DEF = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web for information using a query.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query string",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return (default: 5)",
                    "default": 5
                }
            },
            "required": ["query"],
        },
    },
}
