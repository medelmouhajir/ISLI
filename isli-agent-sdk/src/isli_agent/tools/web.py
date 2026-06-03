from typing import Any
from isli_agent.client import CoreClient


def _get_tool_desc(name: str, default: str) -> str:
    try:
        from isli_agent.prompts_loader import get_prompts
        return get_prompts()["agent"]["tool_descriptions"].get(name, default)
    except Exception:
        return default


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
        "description": _get_tool_desc("web_fetch", "Fetch the content of a website or API from a URL."),
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
        "description": _get_tool_desc("web_search", "Search the web for information using a query."),
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


# ── Browser automation tools (Hermes-style) ──────────────────────────────


async def browser_navigate(
    agent_id: str,
    url: str,
    core_client: CoreClient,
    wait_for_selector: str | None = None,
) -> dict[str, Any]:
    """Navigate the browser to a URL. Creates or reuses a persistent session."""
    payload: dict[str, Any] = {"agent_id": agent_id, "url": url}
    if wait_for_selector is not None:
        payload["wait_for_selector"] = wait_for_selector
    resp = await core_client.client.post(
        "/v1/skills/web-browse-navigate/navigate",
        json=payload,
        headers=core_client._get_headers(),
    )
    resp.raise_for_status()
    return resp.json()

BROWSER_NAVIGATE_DEF = {
    "type": "function",
    "function": {
        "name": "browser_navigate",
        "description": _get_tool_desc(
            "browser_navigate",
            "Navigate a browser to a URL. Must be called before any other browser tool. "
            "Creates a persistent browser session for this agent (cookies/localStorage survive).",
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The absolute URL to navigate to",
                },
                "wait_for_selector": {
                    "type": "string",
                    "description": "Optional CSS selector to wait for after navigation",
                },
            },
            "required": ["url"],
        },
    },
}


async def browser_snapshot(
    agent_id: str,
    core_client: CoreClient,
    full: bool = False,
) -> dict[str, Any]:
    """Take an accessibility-tree snapshot of the current page."""
    resp = await core_client.client.post(
        "/v1/skills/web-browse-snapshot/snapshot",
        json={"agent_id": agent_id, "full": full},
        headers=core_client._get_headers(),
    )
    resp.raise_for_status()
    return resp.json()

BROWSER_SNAPSHOT_DEF = {
    "type": "function",
    "function": {
        "name": "browser_snapshot",
        "description": _get_tool_desc(
            "browser_snapshot",
            "Take an accessibility-tree snapshot of the current browser page. "
            "Returns a compact text representation where interactive elements have @ref IDs like @e1, @e2. "
            "Use these @ref IDs with browser_click and browser_type. "
            "Default returns only interactive elements (buttons, links, inputs). "
            "Set full=true to include all semantic nodes (headings, paragraphs, etc.).",
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "full": {
                    "type": "boolean",
                    "description": "Include all semantic nodes, not just interactive elements",
                    "default": False,
                },
            },
            "required": [],
        },
    },
}


async def browser_click(
    agent_id: str,
    ref: str,
    core_client: CoreClient,
) -> dict[str, Any]:
    """Click an element by its @ref ID from the last snapshot."""
    resp = await core_client.client.post(
        "/v1/skills/web-browse-click/click",
        json={"agent_id": agent_id, "ref": ref},
        headers=core_client._get_headers(),
    )
    resp.raise_for_status()
    return resp.json()

BROWSER_CLICK_DEF = {
    "type": "function",
    "function": {
        "name": "browser_click",
        "description": _get_tool_desc(
            "browser_click",
            "Click an element on the current page by its @ref ID. "
            "The @ref ID comes from the last browser_snapshot call (e.g., @e3).",
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ref": {
                    "type": "string",
                    "description": "The @ref ID of the element to click (e.g., '@e3')",
                },
            },
            "required": ["ref"],
        },
    },
}


async def browser_type(
    agent_id: str,
    ref: str,
    text: str,
    core_client: CoreClient,
    clear: bool = True,
) -> dict[str, Any]:
    """Type text into an input field by its @ref ID."""
    resp = await core_client.client.post(
        "/v1/skills/web-browse-type/type",
        json={"agent_id": agent_id, "ref": ref, "text": text, "clear": clear},
        headers=core_client._get_headers(),
    )
    resp.raise_for_status()
    return resp.json()

BROWSER_TYPE_DEF = {
    "type": "function",
    "function": {
        "name": "browser_type",
        "description": _get_tool_desc(
            "browser_type",
            "Type text into an input field by its @ref ID. "
            "The @ref ID comes from the last browser_snapshot call.",
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ref": {
                    "type": "string",
                    "description": "The @ref ID of the input field (e.g., '@e3')",
                },
                "text": {
                    "type": "string",
                    "description": "The text to type into the field",
                },
                "clear": {
                    "type": "boolean",
                    "description": "Clear the field before typing (default: true)",
                    "default": True,
                },
            },
            "required": ["ref", "text"],
        },
    },
}


async def browser_press(
    agent_id: str,
    key: str,
    core_client: CoreClient,
) -> dict[str, Any]:
    """Press a keyboard key (Enter, Tab, Escape, etc.)."""
    resp = await core_client.client.post(
        "/v1/skills/web-browse-press/press",
        json={"agent_id": agent_id, "key": key},
        headers=core_client._get_headers(),
    )
    resp.raise_for_status()
    return resp.json()

BROWSER_PRESS_DEF = {
    "type": "function",
    "function": {
        "name": "browser_press",
        "description": _get_tool_desc(
            "browser_press",
            "Press a keyboard key in the browser. Useful for submitting forms (Enter), "
            "navigating between fields (Tab), or dismissing dialogs (Escape).",
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "The key to press (e.g., 'Enter', 'Tab', 'Escape', 'ArrowDown')",
                },
            },
            "required": ["key"],
        },
    },
}


async def browser_scroll(
    agent_id: str,
    core_client: CoreClient,
    direction: str = "down",
    amount: int = 3,
) -> dict[str, Any]:
    """Scroll the page up or down."""
    resp = await core_client.client.post(
        "/v1/skills/web-browse-scroll/scroll",
        json={"agent_id": agent_id, "direction": direction, "amount": amount},
        headers=core_client._get_headers(),
    )
    resp.raise_for_status()
    return resp.json()

BROWSER_SCROLL_DEF = {
    "type": "function",
    "function": {
        "name": "browser_scroll",
        "description": _get_tool_desc(
            "browser_scroll",
            "Scroll the browser page up or down to reveal more content.",
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "description": "Direction to scroll: 'up' or 'down'",
                    "default": "down",
                },
                "amount": {
                    "type": "integer",
                    "description": "How much to scroll (larger = more). Default: 3",
                    "default": 3,
                },
            },
            "required": [],
        },
    },
}


async def browser_back(
    agent_id: str,
    core_client: CoreClient,
) -> dict[str, Any]:
    """Navigate back in browser history."""
    resp = await core_client.client.post(
        "/v1/skills/web-browse-back/back",
        json={"agent_id": agent_id},
        headers=core_client._get_headers(),
    )
    resp.raise_for_status()
    return resp.json()

BROWSER_BACK_DEF = {
    "type": "function",
    "function": {
        "name": "browser_back",
        "description": _get_tool_desc(
            "browser_back",
            "Navigate back to the previous page in browser history.",
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}


async def browser_console(
    agent_id: str,
    core_client: CoreClient,
    since_cursor: int = 0,
) -> dict[str, Any]:
    """Return browser console logs captured since the last call."""
    resp = await core_client.client.post(
        "/v1/skills/web-browse-console/console",
        json={"agent_id": agent_id, "since_cursor": since_cursor},
        headers=core_client._get_headers(),
    )
    resp.raise_for_status()
    return resp.json()

BROWSER_CONSOLE_DEF = {
    "type": "function",
    "function": {
        "name": "browser_console",
        "description": _get_tool_desc(
            "browser_console",
            "Retrieve browser console logs captured since the last call. "
            "Pass the next_cursor from the previous response to get delta logs. "
            "Cursor resets on every browser_navigate.",
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "since_cursor": {
                    "type": "integer",
                    "description": "Cursor position from the previous console call. Default: 0",
                    "default": 0,
                },
            },
            "required": [],
        },
    },
}


async def browser_vision(
    agent_id: str,
    core_client: CoreClient,
    question: str | None = None,
) -> dict[str, Any]:
    """Take a screenshot of the current page."""
    payload: dict[str, Any] = {"agent_id": agent_id}
    if question is not None:
        payload["question"] = question
    resp = await core_client.client.post(
        "/v1/skills/web-browse-vision/vision",
        json=payload,
        headers=core_client._get_headers(),
    )
    resp.raise_for_status()
    return resp.json()

BROWSER_VISION_DEF = {
    "type": "function",
    "function": {
        "name": "browser_vision",
        "description": _get_tool_desc(
            "browser_vision",
            "Take a screenshot of the current browser page and return it as a base64-encoded PNG. "
            "Use this when the accessibility tree is insufficient (e.g., CAPTCHAs, canvas content, complex layouts).",
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Optional question about what to look for in the screenshot",
                },
            },
            "required": [],
        },
    },
}


async def browser_get_images(
    agent_id: str,
    core_client: CoreClient,
) -> dict[str, Any]:
    """List all image elements on the current page."""
    resp = await core_client.client.post(
        "/v1/skills/web-browse-images/images",
        json={"agent_id": agent_id},
        headers=core_client._get_headers(),
    )
    resp.raise_for_status()
    return resp.json()

BROWSER_GET_IMAGES_DEF = {
    "type": "function",
    "function": {
        "name": "browser_get_images",
        "description": _get_tool_desc(
            "browser_get_images",
            "List all image elements on the current page with their src URL, alt text, and dimensions.",
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}
