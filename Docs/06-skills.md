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
| `web-search` | Web search → structured results | Uses DuckDuckGo or SerpAPI |
| `web-fetch` | Fetch URL content → clean text | HTML stripped by default |
| `pdf-extract` | Extract text from PDF | Returns paginated JSON |
| `file-read` | Read file from agent's workspace | Path-scoped |
| `file-write` | Write file to agent's workspace | Path-scoped |
| `db-query` | Run read-only SQL query | Scoped to allowed schemas |
| `send-email` | Send email via SMTP | Requires SMTP config |
| `send-message` | Send message via channel | Routes to channel gateway |
| `image-describe` | Get text description of image | Calls local vision model |
| `datetime` | Current date/time in formats | No external calls |
| `json-parse` | Parse and validate JSON | Schema validation support |
| `summarize-text` | Long text → short summary | Calls Keeper endpoint |
| `embed-text` | Text → embedding vector | Calls Keeper endpoint |
| `memory-save` | Save to Tier 3 semantic memory | Calls Keeper endpoint |
| `memory-search` | Search semantic memory | Returns relevant memories |

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

All skills return the same envelope:

```json
{
  "skill_id": "web-search",
  "success": true,
  "data": { ... },          // skill-specific payload
  "error": null,
  "execution_ms": 342,
  "timestamp": "2026-05-10T14:23:00Z"
}
```

On failure:
```json
{
  "skill_id": "web-search",
  "success": false,
  "data": null,
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Too many requests. Retry after 30s.",
    "retry_after": 30
  },
  "execution_ms": 5
}
```

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
- **`file-write` path scoping undocumented** — "Path-scoped" label with no explanation of traversal or symlink prevention.
- **Skill evolution (SkillClaw) is advisory only** — no automated validation that improvement suggestions actually improve outcomes.
- **No per-skill rate limiting** — `rate_limit: 20/minute` in manifest but no enforcement code shown.

> See `Memory/ISLI-Research-Report.md` for full details and recommendations.