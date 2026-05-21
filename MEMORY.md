# Project Memory - ISLI

## Task History

### 2026-05-21: Local Web Search Implementation (SearXNG)
- **Problem:** `web-search` skill was documented but not implemented.
- **Solution:** Integrated SearXNG as a local, self-hosted web search provider.
- **Key Changes:**
  - Added `searxng` service to `docker-compose.yml` (version: `2024.5.15-089760f38`).
  - Created `infra/searxng/settings.yml` with JSON API enabled.
  - Implemented `/search` endpoint in `isli-skills` microservice.
  - Registered `web-search` skill in `isli-core` registry and metadata.
  - Updated `GEMINI.md` to include `web-search` in the project overview.
- **Technical Note:** SearXNG requires `search.formats: [json]` in `settings.yml` for API compatibility.
