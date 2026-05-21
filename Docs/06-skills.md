# 06 — Skills System

## Design Philosophy

> **Skills are smart. Agents are smarter.**

A Skill in ISLI is a **functional capability microservice**:
- **Smart Skills**: Can contain their own AI/LLM loops for domain-specific reasoning.
- **Dumb Skills**: Pure utility microservices (regex, math, formatters).
- Returns structured JSON.
- Minimal, predictable, testable.
- Optimized for fast execution and minimal token consumption.

This allows ISLI to rival frameworks like OpenClaw by permitting skills to handle complex, ambiguous tasks that require internal reasoning before returning a result to the agent.

---

## Skill Manifest (`skill.yaml`)

Every skill is defined by a manifest file:

```yaml
skill:
  id: web-search
  name: "Web Search"
  version: "1.1.0"
  description: "Search the web and return top N results with smart relevance filtering"
  author: system

  endpoint: http://localhost:8101
  health_check: /health
  is_smart: true  # Indicates this skill uses internal AI reasoning
```

  inputs:
    - name: query
      type: string
      required: true
      description: "Search query string"
    - name: max_results
      type: integer
      default: 5
      description: "Maximum results to return"

  outputs:
    - name: results
      type: array
      schema:
        - title: string
        - url: string
        - snippet: string

  permissions_required: []
  rate_limit: 20/minute
  timeout_seconds: 15
```

---

## Built-in Skills Registry

| Skill ID | Description | Notes |
|----------|-------------|-------|
| `web-search` | Web search → structured results | Uses local SearXNG instance |
| `web-fetch` | Fetch URL content → clean text | HTML stripped by default |
| `pdf-extract` | Extract text from PDF | Returns paginated JSON |
| `file-read` | Read file from agent's workspace | Path-scoped, per-agent isolation |
| `file-write` | Write file to agent's workspace | Path-scoped, per-agent isolation |
| `file-list` | List directory entries in agent's workspace | Path-scoped, per-agent isolation |
| `file-delete` | Delete a file from agent's workspace | Path-scoped, per-agent isolation |
| `db-query` | Run read-only SQL query | Scoped to allowed schemas |
| `send-email` | Send email via SMTP | Requires SMTP config |
| `send-message` | Send message via channel | Routes to channel gateway |
| `image-describe` | Get text description of image | Calls local vision model |
| `datetime` | Current date/time in formats | Pure local SDK tool |
| `json-parse` | Parse and validate JSON | Schema validation support |
| `summarize-text` | Long text → short summary | Proxies to Keeper via isli-skills |
| `embed-text` | Text → embedding vector | Proxies to Keeper via isli-skills |
| `memory-save` | Save to Tier 3 semantic memory | Inline in Core (ChromaDB) |
| `memory-delete` | Delete from Tier 3 semantic memory | Inline in Core (ChromaDB) |
| `memory-search` | Search semantic memory | Inline in Core (ChromaDB) |

### Web Search (`web-search`)
The web-search skill provides agents with the ability to perform wide-scale information gathering without relying on external SaaS providers like Google Search API or SerpAPI.

**Implementation Details:**
- **Backend:** Self-hosted **SearXNG** instance.
- **Aggregation:** SearXNG aggregates results from multiple engines (Google, DuckDuckGo) locally.
- **Privacy:** Search queries are routed through your own infrastructure; no direct tracking by external engines.
- **Output:** Returns a clean JSON array of results, each containing a `title`, `url`, and a brief text `snippet`.

**Example Usage (SDK):**
```python
results = await agent.web_search(query="latest ISLI architecture gaps")
```

**Proxy Route:** `POST /v1/skills/web-search/search`

**Skill Types:**
- **External microservice** — `summarize-text`, `embed-text` live in `isli-skills` and are proxied by Core
- **Inline handler** — `memory-save`, `memory-delete`, `memory-search` are handled directly in Core's skill proxy router using `ChromaMemoryClient`; no external service hop
- **Local SDK tool** — `datetime` is a pure Python function in `isli-agent-sdk`; no network call

---

## Skill Invocation Flow

Agents do not call skills directly. All skill calls go through the **Core API skill proxy**:

```
Agent → Core API /api/skills/{skill_id}/invoke (POST)
Core API → validates agent has permission for this skill
Core API → forwards to Skill microservice
Skill microservice → executes, returns JSON
Core API → logs invocation to archive (Tier 4)
Core API → returns response to agent
```

Benefits:
- Central audit log of all skill calls
- Rate limiting enforced at proxy layer
- Skills never know which agent is calling them
- Skills can be hot-swapped without agents knowing

---

## Skill Response Format

External microservice skills return a standard envelope:

```json
{
  "skill_id": "web-search",
  "success": true,
  "data": { ... },
  "error": null,
  "execution_ms": 342,
  "timestamp": "2026-05-10T14:23:00Z"
}
```

Inline handlers (memory skills) and local SDK tools return simpler, domain-specific payloads. For example:

**`memory-save` response:**
```json
{"id": "<uuid>", "collection": "agent_test-agent", "status": "saved"}
```

**`memory-search` response:**
```json
{"ids": [["uuid-1"]], "documents": [["Paris is the capital of France"]], "distances": [[0.21]]}
```

**`summarize-text` response:**
```json
{"summary": "Quick fox jumps over a lazy dog.", "model": "qwen3:1.7b"}
```

On Keeper failure:
```json
{"summary": "<raw input>", "model": "fallback", "note": "Keeper unreachable; returning raw text"}
```

---

## Agent SDK Tool Registry

The `isli-agent-sdk` maintains a central `SKILL_TOOL_REGISTRY` in `isli_agent/tools/__init__.py` that maps normalized skill names to their `(function, definition)` tuples:

```python
from isli_agent.tools import SKILL_TOOL_REGISTRY, normalize_skill_name

# SKILL_TOOL_REGISTRY includes:
#   "send_message", "shell_exec", "web_fetch",
#   "summarize_text", "embed_text", "summarize", "translate",
#   "file_read", "file_write", "file_list", "file_delete",
#   "memory_save", "memory_delete", "memory_search"
```

Skill names from Core (kebab-case like `"send-message"`) are normalized to Python identifiers (`"send_message"`) via `normalize_skill_name()`. The `AgentRunner` uses this registry to auto-populate its toolbox from the synced `config.skills` list.

### Auto-Registration

```python
# Inside AgentRunner.start() — runs automatically
for skill_name in self.config.skills:
    normalized = normalize_skill_name(skill_name)  # "send-message" -> "send_message"
    if normalized in SKILL_TOOL_REGISTRY:
        func, definition = SKILL_TOOL_REGISTRY[normalized]
        self.add_tool(normalized, func, definition)
```

### Convenience Methods

```python
runner.add_workspace_tools()  # file_read, file_write, file_list, file_delete
runner.add_channel_tools()    # send_message
runner.add_system_tools()     # get_current_datetime (always auto-registered)
```

### LiteLLM Tool Definitions

All tool definitions (`FILE_READ_DEF`, `SEND_MESSAGE_DEF`, `MEMORY_SAVE_DEF`, `DATETIME_DEF`, etc.) are exported from their respective `isli_agent.tools.*` modules and from the top-level `isli_agent` package for custom registration:

```python
from isli_agent import send_message, SEND_MESSAGE_DEF
```

### Workspace Tools

Each workspace tool is an async function that calls the Core skill proxy and raises typed exceptions on failure:

| Tool | Exception (404) | Exception (403) | Exception (413) |
|------|----------------|----------------|----------------|
| `file_read` | `WorkspaceNotFoundError` | `WorkspacePathError` | — |
| `file_write` | `WorkspaceNotFoundError` | `WorkspacePathError` | `WorkspaceQuotaError` |
| `file_list` | `WorkspaceNotFoundError` | `WorkspacePathError` | — |
| `file_delete` | `WorkspaceNotFoundError` | `WorkspacePathError` / `WorkspacePermissionError` | — |

These exceptions allow the agent's ReAct loop to recover gracefully instead of crashing on raw HTTP errors.

### Keeper Tools

`summarize_text` and `embed_text` proxy through Core to `isli-skills`, which forwards to Keeper. If Keeper/Ollama is unreachable, they gracefully degrade:
- `summarize_text` returns the raw input text
- `embed_text` returns an empty embedding list

Both require a valid `JWT_SECRET` on the `skills` service to sign internal auth tokens for Keeper communication.

### Memory Tools

`memory_save`, `memory_delete`, and `memory_search` are handled **inline** in Core's skill proxy router (not via an external microservice). Core reads `agent_id` from the request body and calls `ChromaMemoryClient` directly. Collections are scoped per-agent using the `agent_{id}` naming convention.

### System Tools

`get_current_datetime` is a pure Python function that uses `datetime.now(timezone.utc)`. No network call, no auth, no external dependency.

### LiteLLM Tool Definitions

All tool definitions (`FILE_READ_DEF`, `SUMMARIZE_TEXT_DEF`, `MEMORY_SAVE_DEF`, `DATETIME_DEF`, etc.) are exported from their respective `isli_agent.tools.*` modules for custom registration.

---

## Adding a Custom Skill

1. Create a Python FastAPI microservice:

```python
# my-skill/main.py
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class InvokeInput(BaseModel):
    query: str
    max_results: int = 5

@app.post("/invoke")
async def invoke(input: InvokeInput):
    # Your skill logic here — no LLM, no magic
    results = do_the_thing(input.query, input.max_results)
    return {"success": True, "data": results}

@app.get("/health")
async def health():
    return {"status": "ok"}
```

2. Create `skill.yaml` manifest
3. Register via:
```bash
POST /api/skills/register
{ "manifest_url": "http://my-skill:8102/skill.yaml" }
```
4. Skill is immediately available to all permitted agents

---

## Skill Evolution (SkillClaw Pattern)

ISLI implements a simplified version of the **SkillClaw collective evolution** concept:

- Skill invocations are logged with success/failure status
- Keeper periodically analyzes failed invocations
- Keeper generates improvement suggestions stored in Tier 3 memory
- Developer reviews suggestions via Kanban board "Skill Reports" tab

This is **advisory**, not automatic — skills don't rewrite themselves. But the signal is surfaced for human-driven improvement.

---

## Large Output Handling

When a skill returns a large payload (e.g., web-fetch returns 8,000 words):

```
Skill returns large payload to Core API
Core API detects payload > token_threshold (default: 2000 tokens)
Core API calls Keeper /summarize with payload
Keeper summarizes to ≤ 500 tokens
Core API returns summary to agent
Core API stores full payload in Tier 4 archive

Agent receives summary, not full text.
Agent can request full text by calling skill again with `format: full`.
```

This prevents skill outputs from bloating agent context windows.

---

## Skills System Gaps (2026-05-11 Research)

The following gaps were identified during a parallel 12-agent research review:

### Critical
- **Skills have no internal auth or network isolation** — "No auth internally" means any local process can bypass Core API proxy RBAC.
- **`web-fetch` lacks SSRF protections** — no URL blocklists, private IP filtering, or DNS rebinding checks.

### High
- **`db-query` "read-only" not enforced at DB layer** — relies solely on skill code; a bug could allow `DELETE` or `DROP`.
- **No retry policies with exponential backoff** — skill invocation proxy has no documented retry, backoff, or jitter.
- **No structured skill-level observability** — no per-skill latency percentiles, error rates, or payload size logging.

### Medium
- ~~**`file-write` path scoping undocumented**~~ — **Fixed 2026-05-19**. Workspace sandbox (`isli-workspace/src/isli_workspace/sandbox.py`) enforces path traversal blocking via `resolve_path()` + `_ensure_within_workspace()`. Directory deletion is blocked; file size limit is 10 MB; workspace quota is 100 MB.
- **Skill evolution (SkillClaw) is advisory only** — no automated validation that improvement suggestions actually improve outcomes.
- **No per-skill rate limiting** — `rate_limit: 20/minute` in manifest but no enforcement code shown.

> See `Memory/ISLI-Research-Report.md` for full details and recommendations.