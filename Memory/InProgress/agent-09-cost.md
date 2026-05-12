# Research Agent 9 — Cost Economics & Resource Management Findings

**Date:** 2026-05-11
**Scope:** ISLI architecture docs, failure modes, tech stack, agent specification
**Files Reviewed:** `01-architecture.md`, `02-keeper.md`, `03-memory.md`, `04-agents.md`, `05-kanban.md`, `08-failure-modes.md`, `09-tech-stack.md`, `README.md`
**Codebase State:** No implementation files (`.py`) present — review is documentation-only.

---

## Domain Summary

ISLI's cost control mechanisms exist almost entirely at the design-document level, with no visible enforcement code, no cost projections, and no model fallback strategy. The architecture correctly offloads background work to a local Keeper model to reduce cloud token consumption, but it lacks first-class budget governance, leaving the system exposed to the runaway cost scenarios that industry research identifies as a leading cause of agentic-AI project failure.

---

## Findings Table

| ID | Severity | Category | Description | Evidence | Recommendation |
|---|---|---|---|---|---|
| F-01 | Critical | Enforcement | Token budget enforcement (F15) is described in failure-modes docs but **no enforcement code exists** in the repository. The optional daily cap is optional by design and unimplemented. | `08-failure-modes.md` lines 172-181 describe "per-agent token budget enforcement" and "optional daily token cap," yet `04-agents.md` agent turn loop (lines 103-143) contains no budget check, and a full repository search returned zero `.py` files. | Treat cost control as a default-on safety gate, not an option. Implement hard token caps at session, agent, and daily levels in Core API before any agent can call a cloud model. |
| F-02 | High | Planning | **No API cost projections** exist for any deployment scenario. The 10-agents / 100-tasks/day scenario is unmodeled, making budget planning impossible. | No pricing tables, token-per-task estimates, or TCO calculators appear in any document (`04-agents.md`, `09-tech-stack.md`, etc.). | Build a cost estimator using current provider rate cards and per-agent task profiles; publish monthly run-rate projections for common team sizes. |
| F-03 | High | Resilience | **No model fallback strategy** exists when API budgets are exhausted or rate-limited. Agents have a single statically assigned model with no downgrade path. | `04-agents.md` `agent.yaml` schema (lines 35-46) defines one `model_id` and `provider` per agent. No fallback provider, fallback model, or local-model spillover is specified. | Implement a three-tier fallback: expensive cloud model → cheaper cloud model → local Ollama model → automatic pause with Kanban alert. |
| F-04 | High | Accounting | **Delegation chain cost amplification is unmodeled.** A single user request can spawn nested parent/child tasks, each consuming independent cloud tokens, with no cumulative cost rollup. | `05-kanban.md` tracks `token_usage` per task card (lines 51-55) and shows `parent_task_id` delegation links, but there is no chain-level cost aggregation or alert threshold. | Add a root-task cost accumulator that sums token usage across all child tasks; emit a `system:alert` when a root task's delegated cost exceeds a configurable multiplier. |
| F-05 | High | Optimization | **No cost-based model tiering** is implemented. Agents always use their assigned model regardless of task complexity, forgoing the 15× savings production teams achieve via tiering. | `04-agents.md` agent archetypes (lines 162-169) suggest models by role, but the system does not dynamically select a cheaper model for low-complexity tasks. `08-failure-modes.md` F12 discusses multi-model diversity for verification, not cost. | Add a Keeper-side task-complexity score (token estimate, skill count, description embedding similarity to cheap-task patterns) to route trivial tasks to cheaper models automatically. |
| F-06 | Medium | Infrastructure | **Local-model total cost of ownership is unquantified.** Electricity, GPU depreciation, maintenance labor, and hardware replacement cycles are absent from planning docs. | `09-tech-stack.md` lists minimum hardware (lines 149-158) and VRAM estimates, but no TCO model, electricity assumptions, or refresh schedule. | Produce a TCO worksheet including regional electricity rates, hardware amortization over 24-36 months, and ops labor hours for Ollama model updates. |
| F-07 | Medium | Observability | **Cost anomaly detection is underspecified.** "Runaway token usage (3× expected) triggers Kanban alert" has no defined baseline, no threshold config, and no alert routing. | `08-failure-modes.md` line 121 mentions "3× expected" but never defines how "expected" is calculated; `02-keeper.md` line 89 lists "token runaway" as a heartbeat anomaly with no tunable parameters. | Replace static multipliers with per-agent p95 historical baselines; define alert severity levels (warning / critical / halt); route alerts through the existing `system:alert` WebSocket event. |
| F-08 | Medium | Attribution | **Per-agent cost attribution and billing are absent.** Token counts are stored per task, but not aggregated into agent-level or team-level cost dashboards. | `05-kanban.md` shows `token_usage` on the Task interface, but there is no billing schema, cost allocation table, or per-agent spend report in any document. | Add a cost ledger table in PostgreSQL (`agent_id`, `period_start`, `period_end`, `estimated_spend`, `currency`) and surface it on the Kanban Agent Status Bar. |
| F-09 | Medium | Efficiency | **Semantic caching for API call deduplication is missing.** ISLI caches semantic memory reads for 1 hour, but does not cache model responses, leaving 20-40% potential savings unrealized. | `03-memory.md` line 125 notes Redis caching for semantic memory retrieval, but no response-level cache exists in the agent execution loop or Core API. | Implement a response semantic cache keyed by task embedding similarity; serve cached responses when similarity exceeds a threshold (e.g., 0.95) and track hit rate on the board. |
| F-10 | Medium | Governance | **Delegation lacks cost-aware limits.** The `can_delegate_to` graph controls agent topology but imposes no token budgets, depth limits, or cost constraints on delegation chains. | `08-failure-modes.md` F16 (lines 185-191) specifies delegation graph rules in `agent.yaml` but never mentions cost or depth limits. | Enforce a maximum delegation depth and a cumulative subtask token budget per root task in Core API; reject new child tasks that would exceed the parent budget. |
| F-11 | Medium | Architecture | **`token_budget` returned by Keeper is a soft hint, not a hard limit.** The agent SDK is expected to honor it voluntarily, which is unreliable for cost control. | `01-architecture.md` line 94 shows Keeper returns `{ context_injection, token_budget }`, yet `04-agents.md` agent loop does not consume or enforce this value; it is passed to the agent as guidance only. | Move token budget enforcement from the agent SDK to a Core API proxy layer that intercepts model calls and rejects requests that would exceed the remaining budget. |

---

## Cross-Cutting Concerns

1. **Cost treated as failure mode, not first-class concern.** Token runaway appears only in `08-failure-modes.md` (F15) rather than in architecture, agent lifecycle, or Kanban design. This framing makes cost control an afterthought rather than a default safety property.

2. **Industry cost-saving patterns are not architected in.** External production benchmarks show 15× savings from model tiering, 20-40% from semantic caching, and 60-70% from context compression with cheap models. ISLI implements context compression via the Keeper (good) but omits tiering and response caching (bad), leaving most savings on the table.

3. **No defense against Gartner's 40% cancellation risk.** The 2027 prediction that 40% of agentic AI projects will be cancelled due to runaway costs is directly relevant: ISLI lacks the hard budget gates, real-time spend dashboards, and fallback strategies required to keep a multi-agent deployment economically sustainable.

4. **Documentation-only state amplifies risk.** Because no implementation files (`.py`) exist in the repository, every mitigation described is currently a design fiction. The gap between documented intent and working code is 100% for cost governance.

---

## Confidence per Finding

| Finding ID | Confidence | Rationale |
|---|---|---|
| F-01 | Very High | Full-text search of docs and codebase found zero enforcement code; the word "optional" is used explicitly for the daily cap. |
| F-02 | Very High | No cost or pricing content exists in any reviewed document; absence is conclusive. |
| F-03 | Very High | `agent.yaml` schema has exactly one model slot; no fallback fields exist. |
| F-04 | Very High | Task schema shows `token_usage` per task and `parent_task_id`, but no chain-level aggregation or cost fields. |
| F-05 | Very High | Agent archetype table suggests static model assignments; no dynamic routing logic is described. |
| F-06 | High | Hardware specs exist, but TCO requires assumptions not in docs; confidence is high that it is missing, not merely undocumented. |
| F-07 | High | References exist but are vague; certainty that it is underspecified is high, though exact gap magnitude is moderate. |
| F-08 | Very High | No billing or cost aggregation schema exists anywhere; only raw token counts per task. |
| F-09 | High | Semantic memory caching is documented, but response-level deduplication cache is never mentioned. |
| F-10 | Very High | Delegation rules are documented in detail with no cost or depth constraints. |
| F-11 | Very High | Architecture data flow explicitly shows `token_budget` returned, while agent loop ignores it. |

---

*Report prepared by Research Agent 9 (Cost Economics & Resource Management).*
