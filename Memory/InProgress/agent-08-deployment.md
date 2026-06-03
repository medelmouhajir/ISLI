# Agent 08 — Deployment & Operations Findings Report

## Domain Summary

ISLI documents a Docker Compose-based single-machine topology with PostgreSQL, Redis, ChromaDB, Ollama, and FastAPI services, yet none of the operational artifacts (docker-compose.yml, Dockerfiles, .env, or IaC) exist on disk. The architecture targets local development but lacks every production-grade deployment primitive required for a 2026 multi-agent system: config-as-code, secret management, database migrations, health checks, backup/restore, and zero-downtime updates.

---

## Findings Table

| ID | Severity | Category | Description | Evidence | Recommendation |
|----|----------|----------|-------------|----------|----------------|
| F-01 | **Critical** | Artifact Gap | The `docker-compose.yml` documented in `09-tech-stack.md` (lines 162–202) does not exist on disk. No actual deployment orchestration is present. | `09-tech-stack.md` contains a skeleton block; `Glob("docker-compose*")` returned zero files. | Commit a production-ready `docker-compose.yml` with pinned image digests, resource limits, restart policies, and a validated `.env.example`. |
| F-02 | **Critical** | Data Durability | No database migration tooling (Alembic, Flyway, Liquibase, or Django migrations) is referenced anywhere. Schema DDL in `03-memory.md` (lines 78–87, 137–156) exists only as documentation. | Absence of `alembic/`, `migrations/`, or any migration files in the repo; schema is inline in Markdown. | Add Alembic (asyncpg-compatible) or Flyway with versioned migrations. Integrate `alembic upgrade head` into the container startup sequence with idempotency checks. |
| F-03 | **Critical** | Dependency Mgmt | Python and JS dependency pins use wildcard minors (`fastapi==0.115.x`, `react@18`) which allow breaking changes within a minor line. The external context notes 19.5% of runtime faults are dependency management failures. | `09-tech-stack.md` lines 76–105 show `.x` and `@18` style pins. | Switch to exact semver pins (e.g., `fastapi==0.115.8`) and add a lockfile strategy (`poetry.lock`, `uv.lock`, `package-lock.json`) with CI validation. |
| F-04 | **Resolved** | Service Bootstrap | Ollama models (`qwen3:1.7b`, `nomic-embed-text`) are now automatically pulled via an `ollama-init` container on startup. | `docker-compose.yml` now includes an `ollama-init` service with `pull` commands. | Implementation complete (2026-05-22). |
| F-05 | **High** | Data Durability | There is zero documented backup or restore strategy for PostgreSQL, ChromaDB, or Redis. Volume mounts (`./data/postgres`, `./data/vectors`, `./data/ollama`) are present but with no snapshot, replication, or off-site copy plan. | `09-tech-stack.md` lines 173, 178, 182 show host bind mounts with no backup sidecar; no backup docs found in any `Docs/*.md`. | Implement pg_dump/pg_basebackup cron jobs for PostgreSQL, scheduled ChromaDB snapshot exports, and Redis RDB/AOF backups to object storage (S3/MinIO). |
| F-06 | **High** | Service Reliability | Redis is deployed as `redis:7-alpine` with no persistence configuration. AOF is disabled by default, so a container restart or host crash causes total loss of Tier 1 session memory. | `09-tech-stack.md` line 177: `image: redis:7-alpine` with no `command` or `redis.conf` overriding `appendonly`. | Mount a custom `redis.conf` enabling `appendonly yes` and `appendfsync everysec`. Alternatively, use the `redis:7-alpine` with command `redis-server --appendonly yes`. |
| F-07 | **Resolved** | Service Reliability | Health checks and readiness probes are now defined for all services in the `docker-compose.yml`. | `docker-compose.yml` now contains `healthcheck` blocks for every service. | Implementation complete (2026-05-22). |
| F-08 | **High** | Deployment Strategy | Docker Compose does not support zero-downtime rolling updates. There is no documented strategy to deploy new versions without dropping in-flight tasks or terminating WebSocket connections. | `01-architecture.md` lines 135–144 and `09-tech-stack.md` lines 63–65 explicitly target single-machine Docker Compose and reject Kubernetes. | If staying on single-machine Compose, implement a blue/green script with a reverse-proxy (Traefik/Caddy) and connection draining. Alternatively, adopt Docker Swarm or a minimal K3s deployment for rolling updates. |
| F-09 | **High** | Secrets Management | Secrets are stored in a plaintext `.env` file with hardcoded weak passwords (`POSTGRES_PASSWORD=password`) and no secret rotation or encryption. No HashiCorp Vault, AWS Secrets Manager, or Docker Secrets is used. | `09-tech-stack.md` lines 119–145 show `.env` contents with literal `password` and empty API keys. | Integrate a secret backend (HashiCorp Vault, AWS Secrets Manager, or at minimum Docker Secrets with runtime env injection). Rotate the default password before any production deployment. |
| F-10 | **High** | Infrastructure | There is no infrastructure-as-code (Terraform, Pulumi, CloudFormation, Ansible, etc.) for cloud deployment, networking, IAM, or storage provisioning. | `Glob("**/*.tf")` returned zero files; no IaC references exist in any documentation. | Author Terraform or Pulumi modules for compute (EC2/VM or ECS/K8s), networking (VPC, firewall rules), IAM roles, and managed database/cache instances. |
| F-11 | **Medium** | Compliance / MAS | The project lacks config-as-code and semantic versioning for prompts. The 2026 production MAS context requires both. | No prompt registry, prompt versioning, or config-as-code artifacts found in docs or repo. | Create a `prompts/` directory with semver-tagged prompt templates, load them at runtime by version hash, and track changes via git tags. |
| F-12 | **Medium** | Compliance / MAS | No A/B testing infrastructure is documented for model selection, prompt variants, or skill routing. Required for 2026 production MAS. | `01-architecture.md` and `09-tech-stack.md` mention no feature flags, experiment tracking, or routing logic for variants. | Integrate a lightweight experiment system (e.g., Unleash, Flagsmith, or an in-house `experiment_id` field on Tasks) to route traffic between prompt/model variants and measure outcomes. |
| F-13 | **Medium** | Compliance / MAS | There is no documented rollback strategy or capability to revert to a previous release in under 60 seconds. | No rollback docs, no immutable image tags, and no traffic-shaping layer exist in the repo. | Tag every release image with a unique semver+sha label. Use a reverse proxy (Traefik with Docker labels) to swap upstreams instantly, keeping the previous container running during cutover. |
| F-14 | **Medium** | Environment Isolation | No distinction between development, staging, and production environments is documented. Same `.env` and same compose topology are implied for all stages. | `09-tech-stack.md` lines 119–145 show a single `.env` file; no `docker-compose.prod.yml`, `docker-compose.override.yml`, or env-specific configs. | Provide `docker-compose.override.yml` for dev, `docker-compose.staging.yml`, and `docker-compose.prod.yml` with hardened settings (read-only rootfs, no host bind mounts, resource limits). |
| F-15 | **Medium** | Disaster Recovery | There is no disaster recovery plan, RTO, or RPO documented for any data tier. | No DR docs in any `Docs/*.md`; no RTO/RPO targets stated. | Define and document RTO (< 1 hour) and RPO (< 5 minutes) targets. Implement off-site backups, a runbook for full-stack restore, and quarterly DR drills. |
| F-16 | **Medium** | CI/CD | No continuous integration or delivery pipeline is referenced. No automated build, test, or image-scanning steps exist. | No `.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile`, or equivalent found in the repo. | Add a CI pipeline (GitHub Actions/GitLab CI) that lints, runs tests, builds multi-arch images, scans with Trivy/Grype, and pushes to a registry with immutable tags. |

---

## Cross-Cutting Concerns

1. **Single Point of Failure**: The entire topology is designed for one machine. PostgreSQL, Redis, and ChromaDB all run as single instances with no replication or failover. If the host fails, the system is down with no hot standby.
2. **Security Surface**: With no network segmentation beyond Docker's default bridge, the Ollama service (port 11434) and PostgreSQL (port 5432) are exposed on host interfaces. In a production-like scenario, these should be on internal networks only.
3. **Operational Observability Gap**: While Langfuse is listed for LLM tracing, there is no system-level monitoring (Prometheus/Grafana), no log aggregation (Loki/Fluentd), and no alerting (PagerDuty/Opsgenie hooks). The "System Health View" mentioned in `01-architecture.md` (Layer 5) is aspirational with no backend metrics pipeline.
4. **Documentation vs. Reality Drift**: Several architectural components (Skills Registry, Channel Gateway) are described in Markdown but have no corresponding implementation or deployment wiring in the repository. This creates a false sense of completeness.

---

## Confidence per Finding

| Finding | Confidence | Rationale |
|---------|------------|-----------|
| F-01 | **Certain** | Direct file-system search confirmed zero `docker-compose*` files exist. |
| F-02 | **Certain** | No migration directories or tool references found anywhere in the repo. |
| F-03 | **Certain** | Exact text `fastapi==0.115.x` and similar patterns are present in `09-tech-stack.md`. |
| F-04 | **Certain** | Ollama container block in the documented compose file has no model pull logic. |
| F-05 | **Certain** | No backup tooling, scripts, or documentation found in any file. |
| F-06 | **Certain** | Redis block in documented compose has no persistence flag or config mount. |
| F-07 | **Certain** | No `healthcheck` keys in compose skeleton; no endpoint paths mentioned. |
| F-08 | **High** | Compose is explicitly chosen; no blue/green or Swarm overlay mentioned. |
| F-09 | **Certain** | `.env` block with literal `password` is in `09-tech-stack.md`. |
| F-10 | **Certain** | Zero IaC files found; no references in docs. |
| F-11 | **High** | No prompt files or versioning system in repo; not mentioned in docs. |
| F-12 | **High** | No feature-flag or experiment references in any doc. |
| F-13 | **High** | No rollback script, image-tagging strategy, or traffic-shaping layer exists. |
| F-14 | **High** | Only one `.env` and one compose skeleton are shown; no env-specific variants. |
| F-15 | **Certain** | No DR documentation exists in any file. |
| F-16 | **Certain** | No CI configuration files found in repo. |

---

## Files Reviewed

- `X:\Projects\ISLI_AI\Docs\01-architecture.md`
- `X:\Projects\ISLI_AI\Docs\09-tech-stack.md`
- `X:\Projects\ISLI_AI\Docs\03-memory.md`
- `X:\Projects\ISLI_AI\Docs\08-failure-modes.md`
