# 09 — Technology Stack

## Stack Summary

```
Layer               | Technology
--------------------|---------------------------------------------
Local AI            | Ollama (runtime) + qwen3:1.7b + nomic-embed-text
Vector Store        | ChromaDB (local, embedded)
Core API            | Python 3.12 + FastAPI + Uvicorn
Task Queue          | Redis (pub/sub + stream)
Primary Database    | PostgreSQL 16 (pgvector extension)
Session Cache       | Redis
Agent SDK           | Python (custom, minimal)
Frontend            | React 18 + TypeScript + Vite + TailwindCSS
WebSocket           | FastAPI native WebSocket
Container           | Docker + docker-compose
Tracing/Observ.     | Langfuse (self-hosted) or OpenTelemetry
Channels            | python-telegram-bot, Twilio SDK, smtplib
```

---

## Why These Choices

### Python + FastAPI (Core API)
- **Reason**: Python has the richest AI/LLM ecosystem. FastAPI is the de-facto standard for async AI agent backends in 2026.
- **Benchmarks**: FastAPI handles 15,000–20,000 req/s — vastly more than needed.
- **Async-first**: Critical for WebSocket management and concurrent agent handling.
- **Type safety**: Pydantic models prevent malformed payloads from reaching agents.
- **Alternative considered**: Go (faster but no AI ecosystem), Node.js (fine but Python is better for AI-adjacent code).

### Ollama (Local Model Runtime)
- **Reason**: One-command model management. Supports all major quantized models. REST API at `localhost:11434`. No Python dependency conflicts.
- **Key models used**:
  - `nomic-embed-text` (274MB, 8K context, best local embedding quality)
  - `qwen3:1.7b` (summarization, JSON output, fast)
  - `qwen3:0.6b` (heartbeat validation, minimal VRAM)
- **Alternative considered**: llama.cpp directly (more control but more ops overhead).

### ChromaDB (Vector Store)
- **Reason**: Embedded mode (no server needed). Python-native. Excellent for local deployment. Supports cosine similarity + metadata filtering.
- **Why not Weaviate/Qdrant?**: Overkill for a personal/small-team assistant. ChromaDB runs in the same process.
- **Why not PostgreSQL pgvector only?**: pgvector is good for archival but ChromaDB gives better ANN performance for real-time retrieval.

### PostgreSQL 16 (Primary Database)
- **Reason**: The proven choice for durable state in AI agent systems. JSON/JSONB support for flexible task payloads. `pgvector` extension for storing dense embeddings alongside relational data (episodic memory).
- **Why not SQLite?**: ISLI may run multiple concurrent agents. PostgreSQL handles concurrent writes correctly.
- **pgvector**: Used for episodic memory semantic search (Tier 2). Offloads from ChromaDB for long-term.

### Redis (Cache + Event Bus)
- **Reason**: Session memory (Tier 1) needs sub-millisecond reads. Pub/Sub for real-time Kanban events. Stream for task queue.
- **Redis Streams**: Used for task event broadcasting to all connected WebSocket clients.
- **Redis Pub/Sub**: Used for agent heartbeat events.
- **Redis Hash**: Used for session message buffers (with TTL).

### React + TypeScript + Vite (Kanban Board)
- **Reason**: Best DX for real-time UIs. Vite gives fast dev builds. TypeScript prevents UI bugs from bad API responses.
- **@dnd-kit**: Lightweight drag-and-drop for Kanban. No heavy framework.
- **TailwindCSS**: Rapid UI development without fighting CSS.
- **Why not Next.js?**: ISLI board is a single-page app talking to a local API. No SSR needed.

### Docker + docker-compose
- **Reason**: Every component runs in isolation. Easy to start all services with one command. Keeps your PC clean.
- **Not Kubernetes**: ISLI targets single-machine deployment. K8s would be overkill.

### Langfuse (Observability)
- **Reason**: Open-source LLM observability. Traces every agent turn, token usage, latency. Self-hosted.
- **Alternative**: OpenTelemetry + Jaeger (more generic, less LLM-focused).

---

## Dependency Summary

### `isli-core` (Core API)
```
fastapi==0.115.x
uvicorn[standard]==0.30.x
pydantic==2.x
asyncpg==0.30.x       # async PostgreSQL
redis==5.0.x          # async Redis
chromadb==0.5.x
langfuse==2.x
python-jose[cryptography]  # JWT
httpx==0.27.x         # async HTTP for skill calls
```

### `isli-keeper`
```
httpx              # Ollama API calls
chromadb           # vector store
asyncpg            # episodic memory writes
numpy              # embedding operations
fastapi            # keeper internal API
```

### `isli-board` (Frontend)
```
react@18
typescript@5
vite@5
tailwindcss@3
@dnd-kit/core
@tanstack/react-query@5
date-fns@3
```

### Agent SDK
```
httpx              # Core API calls
websockets         # WebSocket connection
pydantic           # config validation
anthropic / openai / google-generativeai  # model clients
```

---

## Environment Variables (`.env`)

```env
# Core API
DATABASE_URL=postgresql://isli:password@localhost:5432/isli
REDIS_URL=redis://localhost:6379
JWT_SECRET=<generate with: openssl rand -hex 32>
KEEPER_URL=http://localhost:8001

# Keeper
OLLAMA_HOST=http://localhost:11434
VECTOR_DB_PATH=./data/vectors

# Langfuse (optional)
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=http://localhost:3000

# Agent API Keys (add as needed)
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GOOGLE_API_KEY=

# Channels (add as needed)
TELEGRAM_BOT_TOKEN=
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
```

---

## Minimum Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| RAM | 8GB | 16GB |
| GPU VRAM (for Keeper models) | 0GB (CPU mode) | 4GB |
| Disk | 10GB | 50GB |
| CPU | 4 cores | 8+ cores |

The full stack runs comfortably on a developer laptop. The Keeper local models (`qwen3:1.7b` + `nomic-embed-text`) together need ~4GB RAM in CPU mode, ~3GB VRAM in GPU mode.

---

## docker-compose.yml (Skeleton)

```yaml
version: '3.9'
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: isli
      POSTGRES_USER: isli
      POSTGRES_PASSWORD: password
    volumes: [./data/postgres:/var/lib/postgresql/data]
    ports: ["5432:5432"]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  ollama:
    image: ollama/ollama:latest
    volumes: [./data/ollama:/root/.ollama]
    ports: ["11434:11434"]
    # Add: deploy.resources.reservations.devices for GPU

  isli-core:
    build: ./isli-core
    depends_on: [postgres, redis]
    ports: ["8000:8000"]
    env_file: .env

  isli-keeper:
    build: ./isli-keeper
    depends_on: [ollama, postgres, redis]
    ports: ["8001:8001"]
    env_file: .env

  isli-board:
    build: ./isli-board
    depends_on: [isli-core]
    ports: ["5173:5173"]
```

---

## Known Infrastructure Gaps (2026-05-11 Research)

The following production-grade infrastructure items are documented in this file but **do not exist on disk** or require implementation:

| Item | Status | Priority | Note |
|------|--------|----------|------|
| `docker-compose.yml` | **Missing on disk** | Critical | Exists only as a Markdown code block above |
| `.env.example` | **Missing on disk** | Critical | No template file for environment variables |
| `requirements.txt` / `pyproject.toml` | **Missing on disk** | Critical | Python dependencies listed but no manifest exists |
| `package.json` (board) | **Missing on disk** | Critical | Frontend dependencies listed but no manifest exists |
| Alembic / Flyway migrations | **Not referenced** | Critical | Database schema only lives in Markdown |
| Health check endpoints | **Undocumented** | High | No `/health`, `/ready`, `/live` for any service |
| OpenTelemetry instrumentation | **Optional ("or Langfuse")** | High | Distributed tracing not mandated |
| CI/CD pipeline | **Missing** | Medium | No `.github/workflows/`, `.gitlab-ci.yml`, etc. |
| Terraform / Pulumi IaC | **Missing** | Medium | No infrastructure-as-code for cloud deployment |
| Secret management (Vault / Docker Secrets) | **Missing** | High | Secrets in plaintext `.env` with literal `password` |
| Redis AOF persistence | **Missing** | High | `redis:7-alpine` runs without `appendonly` |
| Backup/restore strategy | **Missing** | High | No pg_dump, ChromaDB snapshots, or Redis RDB backups |
| Ollama model pre-pull | **Missing** | Critical | First inference call will trigger cold-start download |
| Exact semver lockfiles | **Missing** | Critical | Wildcard minors (`fastapi==0.115.x`) allow breaking changes |

> **Research finding:** The `docker-compose.yml` skeleton above uses `localhost` for inter-service URLs in `.env`, which will break container-to-container networking. In Docker mode, use Compose service names (`postgres`, `redis`, `isli-keeper`) instead of `localhost`. Provide separate `.env.dev` and `.env.prod` templates.
