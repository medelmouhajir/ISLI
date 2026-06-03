---
name: browser-automation-beta
description: Hermes-style browser automation added to ISLI — accessibility tree snapshots, @ref IDs, persistent Playwright sessions, form filling, scrolling, screenshots.
metadata:
  type: project
---

## ISLI Browser Automation (Beta) — Added 2026-06-01

### What It Is
Hermes-style browser automation built into `isli-skills`. Agents can navigate websites, take accessibility-tree snapshots with `@ref` IDs, click/type/scroll, and capture screenshots — all via persistent per-agent Playwright sessions.

### Files Created
- `isli-skills/src/isli_skills/browser/__init__.py`
- `isli-skills/src/isli_skills/browser/exceptions.py` — `BrowserError`, `BrowserRefError`, `BrowserSessionError`
- `isli-skills/src/isli_skills/browser/accessibility_tree.py` — `get_snapshot()` with node-boundary truncation
- `isli-skills/src/isli_skills/browser/session_manager.py` — `BrowserSessionManager` with Redis TTL, cleanup loop, max_concurrent guard
- `isli-skills/src/isli_skills/browser/router.py` — 10 `/browse/*` endpoints
- `isli-skills/tests/test_browser.py` — mocked tests

### Files Modified
- `isli-skills/pyproject.toml` + `requirements.txt` — added `redis[hiredis]>=5.0.0`
- `isli-skills/src/isli_skills/config.py` — browser settings
- `isli-skills/src/isli_skills/main.py` — lifespan init, router mount
- `isli-core/src/isli_core/routers/skills.py` — 10 `web-browse-*` entries in `SKILL_REGISTRY`, `SKILL_METADATA`, `HEAVY_SKILLS`
- `isli-agent-sdk/src/isli_agent/tools/web.py` — 10 browser tool functions + DEF schemas
- `isli-agent-sdk/src/isli_agent/tools/__init__.py` — registrations in `SKILL_TOOL_REGISTRY` + `SKILL_CATEGORY_MAP`
- `docker-compose.yml` — `BROWSER_*` env vars, `browser-sessions` volume, skills memory `1G`
- `Docs/04-agents.md`, `Docs/06-skills.md`, `Docs/09-tech-stack.md`, `Docs/10-roadmap.md`, `README.md`

### Architecture
```
Agent SDK → Core API (skill proxy) → isli-skills:8100/browse/* → Playwright Chromium
                                       ↓
                                  Redis TTL heartbeat
                                  /data/browser-sessions (persistent contexts)
```

### 10 Browser Skills
| Skill | Endpoint | Purpose |
|-------|----------|---------|
| `web-browse-navigate` | `POST /browse/navigate` | Navigate to URL; clears refs before goto |
| `web-browse-snapshot` | `POST /browse/snapshot` | Accessibility tree with `@ref` IDs; `full` flag; 8K truncation |
| `web-browse-click` | `POST /browse/click` | Click by `@ref` ID; 400 if stale |
| `web-browse-type` | `POST /browse/type` | Type text into input by `@ref` ID |
| `web-browse-press` | `POST /browse/press` | Press keyboard key |
| `web-browse-scroll` | `POST /browse/scroll` | Scroll up/down |
| `web-browse-back` | `POST /browse/back` | Go back; clears refs |
| `web-browse-console` | `POST /browse/console` | Delta logs since last call; cursor-based |
| `web-browse-vision` | `POST /browse/vision` | Screenshot as base64 PNG |
| `web-browse-images` | `POST /browse/images` | List `<img>` elements with src/alt/dims |

### Key Behaviors
- **Persistent contexts**: `launch_persistent_context(user_data_dir=...)` per agent — cookies/localStorage survive
- **Ref invalidation**: `session.clear_refs()` called **before** every `navigate` and `back`
- **Compact default**: `full=false` returns only interactive elements; `full=true` for all semantic nodes
- **Node-boundary truncation**: Never cuts mid-line; appends `... N more nodes omitted ...`
- **Console delta**: `page.on("console", ...)` continuously; returns delta since last call; resets on navigate
- **Max concurrent**: `BROWSER_MAX_CONCURRENT_SESSIONS=5` → `503 + Retry-After: 30`
- **Heavy skills**: `web-browse-snapshot` and `web-browse-vision` are `HEAVY_SKILL` → Keeper post-processing

### Board UI
No frontend changes needed. `AgentSkillsPage.tsx` fetches `GET /v1/skills` dynamically. Browser skills appear under the **web** category automatically.

### Docker Compose Env Vars
```yaml
skills:
  BROWSER_REDIS_URL: redis://redis:6379/5
  BROWSER_SESSION_TTL: 600
  BROWSER_HEADLESS: "true"
  BROWSER_SESSION_DIR: /data/browser-sessions
  BROWSER_MAX_CONCURRENT_SESSIONS: 5

core:
  SKILL_WEB_BROWSE_NAVIGATE_URL: http://skills:8100/browse
  ... (9 more)

volumes:
  browser-sessions:
```

### Rebuild Command
```bash
docker compose build core skills agent-runner
docker compose up -d --no-deps core skills
```

**Why:**
- `skills` — new `redis` dependency, new browser module source files
- `core` — new `SKILL_REGISTRY` entries
- `agent-runner` — new SDK tool wrappers compiled into image

### Docs Updated
- `Docs/06-skills.md` — registry table + Browser Automation section
- `Docs/04-agents.md` — sample `agent.yaml` + Browser Automation subsection with example ReAct turn
- `Docs/09-tech-stack.md` — Playwright section in stack table + detailed subsection
- `Docs/10-roadmap.md` — Post-Roadmap Browser Automation (Beta) section
- `README.md` — Phase 9 mention
