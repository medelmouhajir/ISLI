# ISLI Agent SDK

The standard library for building and running ISLI-compatible agents.

## Core Features

- **Auto-Discovery:** Automatically registers tools based on the skills assigned to the agent in the Core API.
- **Dynamic Configuration:** Real-time synchronization of skills, persona, and model settings via WebSockets (zero-restart updates).
- **ReAct Loop:** Built-in support for the ReAct pattern using LiteLLM.
- **Tiered Memory:** First-class support for Episodic, Semantic, and Archival memory.
- **Sandboxed Workspace:** Tools for safe file operations within an isolated workspace.

## Built-in Tools

| Tool | Skill ID | Description |
|------|----------|-------------|
| `web_search` | `web-search` | Search the web using a local SearXNG instance. |
| `web_fetch` | `web-fetch` | Fetch and strip content from a URL. |
| `file_read` | `file-read` | Read files from the agent's sandbox. |
| `file_write` | `file-write` | Write files to the agent's sandbox. |
| `memory_save` | `memory-save` | Save facts to semantic memory. |
| `memory_search`| `memory-search`| Search semantic memory. |
| `send_message` | `send-message` | Send messages to users via channels. |

## Quick Start

```python
from isli_agent import AgentRunner, AgentConfig

config = AgentConfig(
    id="my-agent",
    name="Research Assistant",
    skills=["web-search", "file-write"]
)

runner = AgentRunner(config, core_url="http://localhost:8000")
await runner.start()
```
