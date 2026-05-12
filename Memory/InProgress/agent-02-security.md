# ISLI Security & Threat Modeling Findings — Research Agent 2

**Date:** 2026-05-11
**Scope:** Architecture, Agents, Skills, Channels, Failure Modes documentation
**Methodology:** Document review against 2026 production security baselines (input validation, scoped credentials, sandboxed execution, kill switches, GDPR/HIPAA/SOC 2) and MAST taxonomy threats (prompt injection, credential escalation).

---

## Domain Summary

ISLI is a layered multi-agent system where agents authenticate to a FastAPI Core API via long-lived JWTs and invoke skills through a proxy layer. The architecture assumes a trusted localhost environment and relies heavily on network-boundary security (localhost-only, Core API proxy RBAC) rather than defense-in-depth controls at the skill, database, or prompt layers. This creates significant gaps when the model is moved from single-machine development to production, especially around SSRF, secret rotation, audit logging, and prompt injection containment.

---

## Findings Table

| ID | Severity | Category | Description | Evidence | Recommendation |
|----|----------|----------|-------------|----------|----------------|
| F-01 | **Critical** | Authentication / Network Security | **Ollama local API is unauthenticated.** The Keeper connects to Ollama on localhost with no documented API key or mTLS. Any process with local network access—including a compromised skill or SSRF—can fully control the local model. | `01-architecture.md` states "Keeper → outside world | Never exposed. Localhost only." No `OLLAMA_API_KEY` or proxy auth is mentioned. | Enable Ollama API key authentication; run Ollama behind a local reverse proxy with auth or mTLS; restrict Ollama to a dedicated non-routable socket. |
| F-02 | **Critical** | Network Security / RBAC Bypass | **Skill microservices have no internal authentication and lack network isolation.** Skills are unauthenticated HTTP services on ports 8100–8199. Any local process can call them directly, bypassing the Core API proxy and its RBAC, rate limiting, and audit logging. | `01-architecture.md` Security Boundaries: "Skills | No auth internally. RBAC enforced by Core API proxy." | Deploy skills in isolated Docker networks (only Core API whitelisted); require mTLS or signed requests between Core API and skills. |
| F-03 | **Critical** | Injection / Network Security | **No SSRF protections in `web-fetch` or `web-search`.** A compromised agent can use `web-fetch` to probe internal services, access the unauthenticated Ollama API, reach cloud metadata services (e.g., `169.254.169.254`), or attack the Core API on `localhost:8000`. | `06-skills.md` describes `web-fetch` returning plain text. `08-failure-modes.md` F13 cites HTML stripping but not SSRF. | Implement URL blocklists (localhost, private IPs, metadata IPs), DNS rebinding checks, and a sandboxed HTTP client with no access to internal networks. |
| F-04 | **High** | Data Integrity / Defense in Depth | **`db-query` "read-only" claim is not enforced at the database permission layer.** Enforcement appears to rely solely on the skill microservice code. A bug or compromise in the skill could allow `DELETE`, `DROP`, or `INSERT` against production data. | `06-skills.md` lists `db-query` as "Run read-only SQL query | Scoped to allowed schemas" but no DB-level controls are documented. | Create a dedicated read-only DB role (`GRANT SELECT` only); parse and reject DML/DDL at a query proxy layer; run skill DB connections under the restricted role. |
| F-05 | **High** | Identity and Access Management | **Agent JWTs are long-lived with no rotation strategy.** JWTs are issued once at registration and appear to persist indefinitely. Channel tokens (Telegram, Twilio) are stored in environment variables with no documented rotation schedule. | `04-agents.md` registration flow issues a JWT but never mentions TTL, refresh tokens, or revocation. `07-channels.md` stores secrets in `*_env` vars with no rotation process. | Issue short-lived access tokens (e.g., 1 hour) with refresh tokens; implement automatic rotation for `JWT_SECRET` and channel tokens; provide a token revocation endpoint. |
| F-06 | **High** | Prompt Injection | **User input sanitization is insufficient.** The only documented defense is labeling user input as `[USER INPUT]`. There is no escaping of prompt delimiters, structural containment, or length enforcement. | `08-failure-modes.md` F13: "User input is sanitized and labeled `[USER INPUT]` in agent prompts." `04-agents.md` shows direct f-string interpolation into the system prompt. | Use structural containment (XML/JSON with proper escaping), enforce strict input length limits, and strip/filter known prompt-injection patterns before prompt assembly. |
| F-07 | **High** | Prompt Injection | **Keeper summarization is an unreliable defense against prompt injection via skill outputs.** Malicious content in web-fetched pages can survive or be amplified by summarization. Agents can also bypass summarization entirely with `format: full`. | `08-failure-modes.md` F13 relies on "Keeper's summarization" and that "Keeper is a small local model." `06-skills.md` shows `format: full` bypasses the summary. | Wrap all skill outputs in delimited blocks with escaping; apply a deterministic "no-instructions" output filter; never place untrusted content into system prompts. |
| F-08 | **High** | Authentication / Input Validation | **Webhook secret validation is mentioned but entirely undocumented.** Without signature verification, channel adapters are vulnerable to webhook spoofing and replay attacks. | `01-architecture.md` Security Boundaries: "Channels | Webhook secret validation. Rate limited." `07-channels.md` describes parsing but never secret tokens or HMAC checks. | Document and implement per-platform webhook validation (Telegram `secret_token`, Twilio request signatures, Slack signing secret); reject all unverified webhooks. |
| F-09 | **High** | Identity and Access Management / Threat Modeling | **Blast radius of an exfiltrated agent JWT is broad.** A single JWT grants access to all assigned skills (including `db-query`, `send-email`, `web-fetch`, `file-write`), task creation/delegation, channel messaging, and memory read/write. Data exfiltration is trivial for agents with email + DB access. | `04-agents.md` permissions model grants `skills:invoke`, `channels:send`, `memory:read:own`, `tasks:create`. `agent.yaml` examples show `db-query` and `send-email` co-assigned. | Apply granular per-skill and per-channel permissions; implement behavioral anomaly detection on JWT usage (geo, time, volume); enforce least-privilege by default. |
| F-10 | **Medium** | Compliance / Monitoring | **No audit logging for authentication events or permission changes.** Tier 4 archive logs skill invocations, but agent registration, JWT failures, WebSocket connections, webhook receipt, and scope changes are not documented as logged. | `06-skills.md`: "Core API → logs invocation to archive (Tier 4)." `08-failure-modes.md`: "All skill calls logged in Tier 4 archive." No auth events are mentioned. | Log all authentication events (success/failure), agent lifecycle changes, permission updates, and webhook receipt to a tamper-resistant audit store (append-only, centralized). |
| F-11 | **Medium** | Compliance / Data Protection | **No data retention or encryption-at-rest policies are documented.** User messages, memories, and task outputs persist across PostgreSQL, Redis, ChromaDB, and SQLite. GDPR right-to-erasure and HIPAA safeguards are unaddressed. | `01-architecture.md` lists data stores. `04-agents.md` describes persistent memory scopes. No retention, encryption, or purge mechanisms are documented. | Define retention periods per data tier; enable encryption at rest for all backends; implement automated purge/anonymization workflows for user data deletion requests. |
| F-12 | **Medium** | Input Validation / Path Traversal | **`file-write` path scoping is not documented.** The skill is labeled "Path-scoped" but there is no explanation of how path traversal (e.g., `../../../etc/passwd`) or symlink attacks are prevented. | `06-skills.md` lists `file-write` as "Path-scoped" with no further detail. | Canonicalize paths; enforce a chroot/jail or container-scoped volume; validate against an explicit allowlist of permitted directories. |
| F-13 | **Medium** | Operational Security / Safety | **No global kill switch or emergency pause mechanism exists.** Humans can cancel individual tasks on the Kanban board, but there is no documented way to globally halt all agents, reject new tasks, or sever all WebSockets during a security incident. | `01-architecture.md` and `08-failure-modes.md` mention human inspection and per-task cancellation but no global control. | Implement a global pause/kill switch in Core API that rejects new tasks, closes active agent WebSockets, and blocks skill invocations with an immediate alert. |
| F-14 | **Low** | Access Control | **Delegation graph controls (`can_delegate_to` / `can_receive_from`) are documented in failure modes but missing from agent schema.** This creates ambiguity about whether the controls are actually enforced in agent registration. | `08-failure-modes.md` F16 mentions delegation graph rules. `04-agents.md` `agent.yaml` example and schema do not include these fields. | Update `agent.yaml` schema and registration validation to explicitly require and enforce delegation graph constraints. |

---

## Cross-Cutting Concerns

1. **Localhost Trust Model Breaks in Production.** The architecture repeatedly assumes "localhost = safe" (Keeper, Ollama, skills). In any containerized or cloud deployment, localhost boundaries collapse. An SSRF from `web-fetch`, a compromised container, or a sidecar injection can pivot directly to Ollama or skills.

2. **Core API Proxy Is a Single Point of Compromise.** Because skills rely entirely on the Core API proxy for auth and rate limiting, any bypass of the proxy (direct skill access, network pivot) nullifies all RBAC. The system needs defense-in-depth at the skill and database layers, not just at the proxy.

3. **Prompt Injection Is Treated as a Summarization Problem.** ISLI relies on a local model (Keeper) to sanitize untrusted inputs and skill outputs. This is not a deterministic security control. A determined attacker can craft payloads specifically designed to survive summarization or bypass it via `format: full`.

4. **Compliance Posture Is Undocumented.** SOC 2, GDPR, and HIPAA require access logs, secret rotation, data retention, encryption at rest, and incident response capabilities. None of these are addressed in the current documentation, implying they are either unimplemented or not yet considered.

---

## Confidence per Finding

| ID | Confidence | Rationale |
|----|------------|-----------|
| F-01 | **High** | Explicitly documented as "localhost only"; no Ollama auth mentioned in any file. |
| F-02 | **High** | Security boundaries table explicitly states "No auth internally" for skills. |
| F-03 | **High** | `web-fetch` and `web-search` described with no SSRF mitigations. Architecture maps skill ports as open localhost services. |
| F-04 | **High** | Only skill-level description exists; zero DB permission or query-proxy documentation found. |
| F-05 | **High** | Complete absence of TTL, refresh, or rotation docs across all 5 files. |
| F-06 | **High** | Only mitigation mentioned is `[USER INPUT]` labeling, which is not robust sanitization. |
| F-07 | **High** | Summarization is explicitly cited as the defense; `format: full` bypass is documented. |
| F-08 | **High** | Mentioned in architecture boundaries but entirely absent from channels documentation and config examples. |
| F-09 | **High** | Permissions model and agent YAML examples clearly show broad skill assignment without per-skill granularity. |
| F-10 | **High** | Tier 4 logging is explicitly scoped to skill invocations; no auth or permission change logging is mentioned. |
| F-11 | **Medium** | Data stores are documented but absence of retention/encryption docs may reflect incomplete documentation rather than missing implementation. |
| F-12 | **Medium** | "Path-scoped" label implies some control exists, but the mechanism is undocumented, leaving implementation confidence low. |
| F-13 | **Medium** | No mention of global controls in any doc, but the Kanban human-in-the-loop model may intentionally defer to per-task management. |
| F-14 | **High** | Schema mismatch between failure-modes doc and agent.yaml example is a clear documentation/implementation gap. |

---

*Report generated by Research Agent 2 (Security & Threat Modeling) for ISLI project.*
