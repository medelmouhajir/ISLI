# ISLI Skills Registry

This service provides stateless HTTP microservices that act as "Skills" (tools) for ISLI agents. Agents call these skills through the Core API skill proxy.

## Available Endpoints

### `POST /browse`
Browser automation via Playwright.
- **Input:** `url`, `wait_for_selector` (optional), `screenshot` (bool).
- **Output:** `title`, `content`, `url`, `screenshot_b64` (if requested).

### `POST /search`
Local web search via a self-hosted SearXNG instance.
- **Input:** `query`, `max_results` (default: 5).
- **Output:** `success`, `query`, `results` (list of `title`, `url`, `snippet`).

### `POST /summarize`
Text summarization proxied to the Keeper model.
- **Input:** `text`, `max_length`.
- **Output:** `summary`, `model`.

### `POST /embed`
Vector embedding generation proxied to the Keeper model.
- **Input:** `input`, `model`.
- **Output:** `embedding`, `model`.

## Configuration

The service is configured via environment variables:
- `SEARXNG_URL`: URL of the SearXNG instance (default: `http://localhost:8080/search`).
- `KEEPER_URL`: URL of the Keeper service (default: `http://localhost:8001`).
- `WORKSPACE_URL`: URL of the Workspace service (default: `http://localhost:8300`).
- `JWT_SECRET`: Secret for verifying internal auth tokens.
