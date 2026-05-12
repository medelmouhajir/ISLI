# Agent Coordination & Communication — Gap Analysis Report

**Date:** 2026-05-11
**Agent:** Research Agent 06 — Agent Coordination & Communication
**Scope:** ISLI Docs 04-agents, 05-kanban, 01-architecture, 08-failure-modes

---

## Domain Summary

ISLI uses a Kanban board as its sole inter-agent communication protocol, eliminating direct agent-to-agent calls and ensuring full auditability. However, the system lacks distributed-concurrency safeguards — no deadlock detection, queue limits, delegation chain bounds, or active challenge mechanisms — which creates critical coordination gaps as delegation depth and agent count grow.

---

## Findings Table

| ID | Severity | Category | Description | Evidence | Recommendation |
|----|----------|----------|-------------|----------|----------------|
| F-01 | **Critical** | Delegation Safety | No transitive delegation cycle detection. The `can_delegate_to`/`can_receive_from` lists (F16 mitigation) enforce allowed edges but do not prevent or detect cycles such as A→B→C→A. A cyclic delegation would spawn infinite tasks with no terminating condition. | `08-failure-modes.md` lines 188-191: Core API "rejects delegation attempts from agents not in the allowed graph" — no mention of DAG validation or cycle detection. `04-agents.md` lines 30-78: `agent.yaml` defines delegation graph locally with no cross-agent cycle check. | Enforce DAG property at agent registration; add runtime cycle detection before any `tasks:create` delegation event. Reject cycles with a `system:alert`. |
| F-02 | **High** | Timeout & Reliability | No global timeout for multi-agent delegation chains. Individual tasks auto-expire after `task_timeout_seconds` (default 5 min), but an agent waiting for a child task that itself delegates has no cumulative chain timeout. Agent A could remain BLOCKED indefinitely. | `08-failure-modes.md` lines 84-88: task auto-expires after 5 min, but only per-task. `01-architecture.md` lines 118-126: Agent A "waits for card status = Done" with no chain-level expiry. `04-agents.md` lines 19-24: BLOCKED state has no associated timeout. | Add `chain_timeout_seconds` tracked across `parent_task_id`→`child_task_ids` lineage; abort entire chain and surface alert on Kanban when exceeded. |
| F-03 | **Medium** | Scheduling Fairness | No priority inversion detection. Tasks carry priority levels 1-5, yet there is no mechanism to detect when a low-priority task occupies an agent while a higher-priority task sits in ASSIGNED or INBOX. | `05-kanban.md` lines 31-58: `Task` interface includes `priority: 1 | 2 | 3 | 4 | 5`. No inversion detection is described in board behavior or Core API logic. `04-agents.md` lines 176-189: permission model covers task CRUD but not scheduling policy. | Implement a priority-inversion monitor that flags when an agent's active task has lower priority than another task assigned to that agent. Auto-preempt or alert human. |
| F-04 | **Medium** | Capacity Planning | No Kanban queue depth limit per agent. An agent can accumulate unlimited ASSIGNED tasks, risking overload, latency spikes, and silent buffer exhaustion. | `05-kanban.md` lines 13-24: board columns defined without capacity limits. `04-agents.md` lines 16-24: agent lifecycle shows IDLE→ACTIVE transitions but no queue length gate. `01-architecture.md` lines 118-126: task creation is unconstrained by agent load. | Add `max_assigned_tasks` to `agent.yaml`; when exceeded, overflow tasks remain in INBOX with a `system:alert`. |
| F-05 | **Critical** | Accuracy Degradation | Unbounded delegation chain length. Per 2026 research, chains beyond 3 agents suffer exponential relay degradation, and a 5-agent relay achieves only ~22.5% accuracy. ISLI tracks parent/child links but enforces no maximum depth. | `05-kanban.md` lines 119-127: delegation visualization shows parent→child links. `08-failure-modes.md` lines 127-134 (F11): mentions visible chains but no depth bound. `01-architecture.md` lines 118-126: inter-agent delegation described without depth limit. | Hard-limit delegation depth to 3. Require explicit human approval (Kanban prompt) for depth 2+. Add `chain_depth` field to Task schema. |
| F-06 | **High** | Consensus & Verification | Insufficient defense against consensus inertia. F6 mitigations (agent isolation, multi-model diversity, judge agents) are passive; there is no active "Challenge" step as prescribed by BICR governance. External research shows consensus inertia accumulates 3.9 confirming contexts by round 6, and BICR reduces cascade probability 3.4×. | `08-failure-modes.md` lines 69-78 (F6): mitigations are isolation and model diversity — no explicit dissent-forcing or challenge round. No BICR concepts appear in any document. | Integrate BICR governance: add a mandatory "Challenge" phase for high-stakes tasks where a designated challenger agent must attempt to falsify the output before consensus. |
| F-07 | **Medium** | Fault Tolerance | No guard against delegating to offline agents. If Agent A creates a delegation task for Agent B while B is OFFLINE, the task sits in ASSIGNED indefinitely with no rejection, retry, or TTL. | `04-agents.md` lines 16-24: OFFLINE state exists in lifecycle but no transition rules prevent assignment. `05-kanban.md` lines 62-76: status bar shows offline agents, yet no auto-rejection logic is described. `01-architecture.md` lines 34-42: Core API responsibilities include task creation but not offline-guard. | Core API should reject `tasks:create` assignments to OFFLINE agents, returning `agent:offline` error. Alternatively, queue with a TTL and escalate to human if agent does not come ONLINE. |
| F-08 | **High** | Concurrency Control | No deadlock detection for inter-agent waits. Agent A enters BLOCKED waiting for Agent B's task; if B simultaneously delegates back to A (or via a longer cycle), both agents deadlock with no breaker. | `04-agents.md` lines 19-24: BLOCKED state defined as "waiting for delegation". `01-architecture.md` lines 118-126: Agent A waits for Agent B with no timeout or cycle check. No wait-for graph or deadlock detection is mentioned in any doc. | Maintain a runtime wait-for graph of agent→task dependencies. Detect cycles and abort the youngest task in the cycle, surfacing a `system:alert`. |
| F-09 | **Medium** | Resource Contention | No mechanism for simultaneous conflicting task assignments. Two tasks assigned to the same agent may target the same external resource or contradict each other's goals, with no conflict detection or resolution. | `05-kanban.md` lines 100-115: human actions include reassign and cancel, but no automatic conflict detection. `04-agents.md` lines 176-189: agents have scoped permissions but no resource-lock or task-compatibility check. | Add optional `resource_lock` and `conflicts_with` fields to Task schema; Core API should flag or serialize conflicting assignments. |
| F-10 | **Medium** | Observability | No monitoring for exponential relay degradation. Token usage is tracked per task (F15), but there is no telemetry on delegation chain length, semantic drift between parent intent and child output, or relay accuracy decay. | `08-failure-modes.md` lines 175-181 (F15): token budget enforcement exists. `05-kanban.md` lines 31-58: Task schema lacks `chain_depth` or `relay_drift_score`. No metric correlates chain length with output quality. | Add `chain_depth`, `relay_drift_score`, and `semantic_fidelity` metrics to task telemetry. Alert when drift exceeds threshold or depth exceeds 2. |

---

## Cross-Cutting Concerns

1. **Kanban-as-Protocol Introduces Distributed-State Concurrency Risks**
   Eliminating direct agent calls improves observability, but the resulting shared-state model (tasks as messages, BLOCKED as waits, ASSIGNED as queues) inherits classic distributed-system hazards — deadlocks, priority inversion, unbounded buffers, and cascade failures — none of which are addressed in the current design. The system needs concurrency-control primitives (queue caps, wait-for graphs, chain timeouts) at the Core API layer, not just Kanban UI features.

2. **BICR Governance Partially Implemented**
   The 2026 external research identifies BICR (Buffer, Isolate, Challenge, Recover) as a 3.4× reducer of cascade probability. ISLI implements "Isolate" well (agent separation, multi-model diversity, judge isolation), but the other three pillars are missing:
   - **Buffer** (F-04): no queue-depth limits to absorb shock.
   - **Challenge** (F-06): no active dissent mechanism to break false consensus.
   - **Recover** (F-02, F-05): no chain rollback or bounded retry to recover from deep-delegation failures.
   Closing these three gaps would bring ISLI into alignment with the proven BICR framework.

3. **Human-in-the-Loop Is Over-Relied Upon for Systemic Failures**
   Many mitigations (visible chains, human cancel, board alerts) assume a human is watching the Kanban board in real time. For systemic failures like deadlocks (F-08) or delegation cycles (F-01), human reaction time is too slow. The architecture should treat these as machine-resolvable failures with automatic breakers, using human notification only as a secondary step.

---

## Confidence per Finding

| Finding | Confidence | Rationale |
|---------|------------|-----------|
| F-01 | **High** | Explicit delegation graph rules exist; absence of cycle detection is a clear, unambiguous gap. |
| F-02 | **High** | Per-task timeout is documented; chain timeout is never mentioned. Waiting semantics in architecture docs confirm the gap. |
| F-03 | **Medium** | Priority field exists; inversion detection is absent but could theoretically live in an unshown scheduler module. |
| F-04 | **High** | No queue limit is mentioned in any column, schema, or API behavior description. |
| F-05 | **High** | Parent/child links are explicit; depth bound is absent. External research provides strong quantitative justification. |
| F-06 | **Medium** | F6 mitigations are present but passive. BICR is not mentioned, making the gap likely but the severity dependent on external research. |
| F-07 | **High** | Offline state and delegation mechanics are both documented, but no guard linking them is described. |
| F-08 | **High** | BLOCKED state and delegation waits are documented; deadlock detection is entirely absent. |
| F-09 | **Medium** | No explicit conflict mechanism is described, though it is possible unshown Core API logic handles it. |
| F-10 | **High** | Token metrics exist; chain-quality metrics are completely absent from schemas and failure-mode docs. |

---

## Recommendations Summary (Prioritized)

1. **Immediate (Critical):** Implement delegation DAG validation (F-01) and chain depth hard limit (F-05). These prevent infinite loops and catastrophic accuracy collapse.
2. **Short-term (High):** Add chain-level timeouts (F-02) and deadlock detection (F-08) to unblock agents automatically.
3. **Medium-term (Medium):** Add queue depth limits (F-04), offline-agent guards (F-07), and priority-inversion alerts (F-03).
4. **Research (Medium):** Design and prototype a BICR Challenge phase (F-06) and conflict-resolution schema (F-09).
5. **Observability (Ongoing):** Deploy relay-degradation telemetry (F-10) to measure real-world chain quality and inform depth-limit tuning.
