# ISLI Browser (Beta) — Implementation Plan

## Goal
Add Hermes-style browser automation to ISLI: accessibility-tree snapshots, element ref IDs, clicking, typing, scrolling, and vision fallback. Phase 1 focuses on `navigate` + `snapshot` (80% of browsing power). Phase 2 adds interaction primitives. Phase 3 adds vision.

## Architecture

```
Agent SDK ──► Core API (skill proxy) ──► isli-skills:8100/browse/* ──► Playwright Chromium
                                       │
                                       └── Redis TTL tracking
                                       └── /data/browser-sessions (persistent contexts)
```

## Files to Create

### 1. `isli-skills/src/isli_skills/browser/__init__.py`
Empty init.

### 2. `isli-skills/src/isli_skills/browser/session_manager.py`
- `BrowserSession` dataclass: `context`, `page`, `ref_map: dict[str, Any]`, `last_accessed: float`, `lock: asyncio.Lock`
- `BrowserSessionManager`:
  - `__init__(redis_url, playwright, session_dir, ttl_seconds=600, max_concurrent=5)`
  - `async def get_or_create(agent_id) -> BrowserSession`
    - If `len(_sessions) >= max_concurrent`, raise `BrowserSessionError("Browser session pool exhausted. Max concurrent: {max_concurrent}.")` — router catches and returns `503` with `Retry-After: 30`.
  - `async def close_session(agent_id)`
  - `async def touch(agent_id)` — refresh Redis TTL
  - `async def cleanup_loop()` — background task every 60s, close stale sessions
  - Uses `launch_persistent_context(user_data_dir=f"{session_dir}/{agent_id}")` so cookies/localStorage survive across calls
  - In-memory `_sessions: dict[str, BrowserSession]` (Playwright objects can't be serialized)
  - Redis used only for TTL heartbeat (`browser:session:{agent_id}`) and cross-instance awareness

### 3. `isli-skills/src/isli_skills/browser/accessibility_tree.py`
- `async def get_snapshot(page, ref_map: dict, full=False, max_chars=8000) -> str`
  - Calls `page.accessibility.snapshot()`
  - **Default `full=False` (compact mode)**: only includes interactive elements — button, link, input, select, textarea, checkbox, radio. This is the Hermes default and keeps snapshots small and focused on actionable items.
  - **`full=True`**: includes all semantic nodes — headings, paragraphs, lists, tables, landmarks. Agent must explicitly request this.
  - Traverses tree recursively, assigns `@e1`, `@e2`, ... only to interactive elements (even in `full=True` — non-interactive nodes get `[N]` labels but no `@ref`)
  - Returns compact text representation:
    ```
    [1] heading "Welcome to Example"
    [2] input[text] "Email" @e1 (placeholder: "you@example.com")
    [3] button "Sign in" @e2
    [4] link "Forgot password?" @e3 href="/reset"
    ```
- **Snapshot size guard — node boundary truncation**: Build snapshot line-by-line, stop after the line that pushes cumulative length over `max_chars`. Never cut mid-line. Append `\n[... {N} more nodes omitted ...]` so the agent knows context is incomplete.
- `def flatten_tree(node, lines, ref_counter, full, max_chars)` — recursive helper
- Stores mapping `ref_id -> element_handle` in the session's `ref_map`
- **Snapshot invalidation on navigate**: `BrowserSessionManager.get_or_create()` returns a fresh page after navigation, but the router's `navigate` handler must explicitly call `session.clear_refs()` **before** `page.goto()` to prevent a slow agent from sending a click `@e3` that hits a completely different element on the new page.

### 4. `isli-skills/src/isli_skills/browser/router.py`
FastAPI router with prefix `/browse`:

| Endpoint | Request Body | Response |
|----------|-------------|----------|
| `POST /browse/navigate` | `{agent_id, url, wait_for_selector?}` | `{url, title, status_code}` |
| `POST /browse/snapshot` | `{agent_id, full?}` | `{snapshot: str, url}` |
| `POST /browse/click` | `{agent_id, ref}` | `{success, url}` |
| `POST /browse/type` | `{agent_id, ref, text, clear?}` | `{success, url}` |
| `POST /browse/press` | `{agent_id, key}` | `{success, url}` |
| `POST /browse/scroll` | `{agent_id, direction, amount?}` | `{success, url}` |
| `POST /browse/back` | `{agent_id}` | `{success, url}` |
| `POST /browse/console` | `{agent_id, since_cursor?}` | `{logs: list[dict], next_cursor: str}` |
| `POST /browse/vision` | `{agent_id, question?}` | `{description, screenshot_b64?}` |
| `POST /browse/images` | `{agent_id}` | `{images: list[dict]}` |

All endpoints:
- `Depends(require_internal_auth)`
- Call `session_mgr.get_or_create(agent_id)` to get the page
- On success, call `session_mgr.touch(agent_id)`
- On element interactions (`click`, `type`), look up `ref` in `session.ref_map`; if missing -> `400 Ref not found — re-run snapshot`

**Console endpoint behavior**: Captures logs continuously via Playwright's `page.on("console", ...)` listener. Each `POST /browse/console` returns only the **delta since the last call** (or since `navigate` if first call). Returns `{"logs": [...], "next_cursor": "<token>"}`. The agent passes `since_cursor` on subsequent calls. Cursor resets on every `navigate`.

### 5. `isli-skills/src/isli_skills/browser/exceptions.py`
- `BrowserError(Exception)`
- `BrowserRefError(BrowserError)` — stale or unknown ref ID
- `BrowserSessionError(BrowserError)` — session creation/closure failure

### 6. `isli-skills/tests/test_browser.py`
- Mock `BrowserSessionManager` or use `unittest.mock` on Playwright
- Test `navigate`, `snapshot`, `click` with mocked page/context
- Test ref-not-found error

## Files to Modify

### 7. `isli-skills/src/isli_skills/main.py`
- Import and mount the browser router: `app.include_router(browser_router, prefix="/browse")`
  Wait — the router already has prefix `/browse`, and we want the endpoints to be `/browse/navigate`, etc. So we mount at root: `app.include_router(browser_router)`.
- Keep existing `/browse` (orphaned) and `/fetch` endpoints as-is for backward compatibility. Actually, `POST /browse` conflicts with the router prefix. The router defines `/browse/navigate`, `/browse/snapshot`... but if we mount the router at root, `/browse` still exists as the old endpoint. This is fine — they don't conflict since old `/browse` is exact match and new ones are `/browse/*`.
- Add lifespan startup: initialize Playwright + BrowserSessionManager; start cleanup background task.
- Add lifespan shutdown: close all browser sessions + stop Playwright.

### 8. `isli-skills/src/isli_skills/config.py`
Add fields:
- `browser_headless: bool = True`
- `browser_session_ttl: int = 600`
- `browser_session_dir: str = "/tmp/browser-sessions"`
- `browser_max_snapshot_chars: int = 8000`
- `browser_redis_url: str = ""` (falls back to `redis_url`)
- `browser_max_concurrent_sessions: int = 5` — hard cap on active BrowserContext instances

### 9. `isli-skills/pyproject.toml`
Add `redis[hiredis]>=5.0.0` to dependencies.

### 10. `isli-skills/requirements.txt`
Add `redis[hiredis]>=5.0.0` (keep in sync with pyproject.toml).

### 11. `isli-core/src/isli_core/routers/skills.py`
Add to `SKILL_REGISTRY`:
```python
"web-browse-navigate": os.getenv("SKILL_WEB_BROWSE_NAVIGATE_URL", "http://localhost:8100/browse"),
"web-browse-snapshot": os.getenv("SKILL_WEB_BROWSE_SNAPSHOT_URL", "http://localhost:8100/browse"),
"web-browse-click": os.getenv("SKILL_WEB_BROWSE_CLICK_URL", "http://localhost:8100/browse"),
"web-browse-type": os.getenv("SKILL_WEB_BROWSE_TYPE_URL", "http://localhost:8100/browse"),
"web-browse-press": os.getenv("SKILL_WEB_BROWSE_PRESS_URL", "http://localhost:8100/browse"),
"web-browse-scroll": os.getenv("SKILL_WEB_BROWSE_SCROLL_URL", "http://localhost:8100/browse"),
"web-browse-back": os.getenv("SKILL_WEB_BROWSE_BACK_URL", "http://localhost:8100/browse"),
"web-browse-console": os.getenv("SKILL_WEB_BROWSE_CONSOLE_URL", "http://localhost:8100/browse"),
"web-browse-vision": os.getenv("SKILL_WEB_BROWSE_VISION_URL", "http://localhost:8100/browse"),
"web-browse-images": os.getenv("SKILL_WEB_BROWSE_IMAGES_URL", "http://localhost:8100/browse"),
```

Add to `SKILL_METADATA`:
```python
"web-browse-navigate": {"description": "Navigate a browser to a URL.", "type": "external", "category": "web"},
"web-browse-snapshot": {"description": "Take an accessibility-tree snapshot of the current page.", "type": "external", "category": "web"},
...
```

Add to `HEAVY_SKILLS`:
```python
HEAVY_SKILLS = {"web-fetch", "shell-exec", "web-browse-snapshot", "web-browse-vision"}
```

### 12. `isli-agent-sdk/src/isli_agent/tools/web.py`
Add tool functions + definitions:
```python
async def browser_navigate(agent_id, url, core_client, wait_for_selector=None): ...
BROWSER_NAVIGATE_DEF = {...}

async def browser_snapshot(agent_id, core_client, full=False): ...
BROWSER_SNAPSHOT_DEF = {...}

async def browser_click(agent_id, ref, core_client): ...
BROWSER_CLICK_DEF = {...}

async def browser_type(agent_id, ref, text, core_client, clear=True): ...
BROWSER_TYPE_DEF = {...}

async def browser_press(agent_id, key, core_client): ...
BROWSER_PRESS_DEF = {...}

async def browser_scroll(agent_id, core_client, direction="down", amount=3): ...
BROWSER_SCROLL_DEF = {...}

async def browser_back(agent_id, core_client): ...
BROWSER_BACK_DEF = {...}

async def browser_console(agent_id, core_client): ...
BROWSER_CONSOLE_DEF = {...}

async def browser_vision(agent_id, core_client, question=None): ...
BROWSER_VISION_DEF = {...}

async def browser_get_images(agent_id, core_client): ...
BROWSER_GET_IMAGES_DEF = {...}
```

### 13. `isli-agent-sdk/src/isli_agent/tools/__init__.py`
- Import all new browser tools
- Add entries to `SKILL_TOOL_REGISTRY` mapping normalized names (`browser_navigate`, etc.) to `(func, def)` tuples
- Add entries to `SKILL_CATEGORY_MAP`

### 14. `docker-compose.yml`
**`skills` service:**
Add environment:
```yaml
BROWSER_REDIS_URL: redis://redis:6379/5
BROWSER_SESSION_TTL: 600
BROWSER_HEADLESS: "true"
BROWSER_SESSION_DIR: /data/browser-sessions
BROWSER_MAX_CONCURRENT_SESSIONS: 5
```
Add volume:
```yaml
volumes:
  - browser-sessions:/data/browser-sessions
```
Increase memory limit from `512M` to `1G` (Chromium needs more).

**`core` service:**
Add environment:
```yaml
SKILL_WEB_BROWSE_NAVIGATE_URL: http://skills:8100/browse
SKILL_WEB_BROWSE_SNAPSHOT_URL: http://skills:8100/browse
SKILL_WEB_BROWSE_CLICK_URL: http://skills:8100/browse
SKILL_WEB_BROWSE_TYPE_URL: http://skills:8100/browse
SKILL_WEB_BROWSE_PRESS_URL: http://skills:8100/browse
SKILL_WEB_BROWSE_SCROLL_URL: http://skills:8100/browse
SKILL_WEB_BROWSE_BACK_URL: http://skills:8100/browse
SKILL_WEB_BROWSE_CONSOLE_URL: http://skills:8100/browse
SKILL_WEB_BROWSE_VISION_URL: http://skills:8100/browse
SKILL_WEB_BROWSE_IMAGES_URL: http://skills:8100/browse
```

**Top-level volumes:**
Add `browser_sessions:`

## Implementation Order

1. `isli-skills` dependencies (`redis` in pyproject.toml + requirements.txt)
2. `isli-skills` browser module (`exceptions.py`, `accessibility_tree.py`, `session_manager.py`, `router.py`)
3. Wire browser router into `isli-skills/main.py` + config updates
4. `isli-core` skill registry + metadata + HEAVY_SKILLS updates
5. `isli-agent-sdk` tool wrappers + registry updates
6. `docker-compose.yml` env vars + volume + memory bump
7. Tests for browser endpoints

## Key Design Decisions

1. **Session store**: In-memory dict of Playwright objects; Redis only for TTL heartbeat. This is necessary because BrowserContext/Page/ElementHandle cannot be serialized. The trade-off: `isli-skills` must run as a single instance for browser sessions to persist. This is acceptable for the Beta.

2. **Ref ID round-tripping**: During `snapshot`, we walk the accessibility tree, assign `@eN` IDs, and store `ref_map["eN"] = element_handle` in the session. `click`/`type` look up the handle. If the page navigated and the handle is stale, Playwright will raise; we catch and return `BrowserRefError` telling the agent to re-snapshot.

3. **Snapshot size guard — node boundary truncation**: Build snapshot line-by-line, stop after the line that pushes cumulative length over `max_chars`. Never cut mid-line. Append `\n[... {N} more nodes omitted ...]` so the agent knows context is incomplete. **Default `full=False`** (interactive elements only) means most pages stay well under the limit without truncation.

3b. **Snapshot invalidation on navigate**: `session.clear_refs()` is called **before** `page.goto()` in the navigate handler. This prevents a slow agent from sending a click `@e3` that hits a completely different element on the new page.

4. **Persistent contexts**: `launch_persistent_context(user_data_dir=...)` gives each agent their own browser profile (cookies, localStorage). The user data dir is on the `browser-sessions` volume.

5. **Max concurrent sessions guard**: `BROWSER_MAX_CONCURRENT_SESSIONS=5` with `503 + Retry-After: 30` when exceeded. Prevents silent OOM kills when multiple agents (Zero, Harvey, Butler) spawn browsers simultaneously.

6. **Console log scope**: Continuous capture via `page.on("console", ...)`. `POST /browse/console` returns only the delta since the last call (cursor-based). Cursor resets on every `navigate` so old page logs don't leak into the new page.

7. **Backward compatibility**: Old `POST /browse` and `POST /fetch` in `isli-skills/main.py` remain untouched. They are not wired into Core and will continue to work for direct callers.

## Rollback Plan
- Remove browser env vars from `docker-compose.yml`
- Revert `SKILL_REGISTRY` additions in `isli-core`
- The `isli-skills` changes are additive and won't break existing endpoints

## Testing Strategy
- `test_browser.py` with mocked Playwright page/context
- Integration: spin up stack, send `/v1/skills/web-browse-navigate/navigate` via Core proxy, verify 200
- Manual: Agent with `web-browse-navigate` and `web-browse-snapshot` in its `skills` list should auto-register tools and be able to browse example.com
