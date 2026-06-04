# Service Mesh Backlog
## Deferred: Zero-Trust mTLS for Multi-Host Deployments

### Status: **Intentionally Deferred**

This document preserves the full service mesh architecture design. It is **not** scheduled for implementation while ISLI remains on single-host Docker Compose. Revisit when migrating to Kubernetes or multi-host Docker Swarm.

### Why Deferred

Running a full service mesh (Consul Connect, Linkerd, or Istio) on a single Docker host introduces significant operational overhead without proportional security gains:

- **Sidecar tax**: 6–8 extra containers for Envoy proxies + control plane
- **Local dev friction**: `network_mode: service:*` breaks individual service debugging
- **Limited blast-radius value**: Single-host boundary already contains lateral movement
- **Debugging complexity**: "Is it the app, the sidecar, the intention, or the cert?"

### Decision Criteria for Revisiting

Reactivate this backlog when **any** of the following occur:

1. ISLI deploys to **Kubernetes**
2. ISLI deploys to **multi-host Docker Swarm**
3. A third-party security audit flags the **lack of mTLS** as a blocking issue for a specific enterprise contract

### Recommended Technology

| Runtime | Recommendation | Rationale |
|---------|----------------|-----------|
| Docker Compose (current) | **None** — application-layer auth + network segmentation is sufficient | See `Docs/16-security-runbook.md` |
| Kubernetes | **Linkerd** | Automatic sidecar injection, native `AuthorizationPolicy`, better gRPC/HTTP2 |
| Docker Swarm | **Consul Connect** | First-class non-K8s support, built-in CA |

### What the Mesh Would Provide

1. **Automatic mTLS** on all east-west traffic
2. **Dynamic service discovery** replacing env-var URLs
3. **Zero-trust intentions** (default-deny service-to-service policies)
4. **Per-pod SPIFFE identities** replacing shared-secret JWT
5. **Certificate auto-rotation** (no manual cert management)

### Migration Path from Current State

When the time comes, the migration is incremental:

1. **Application auth is already hardened** — Phase 1 of the security sprint (auth bypass fixes, empty-JWT removal) transfers directly
2. **ServiceDiscovery utility** (`isli-core/src/isli_core/discovery.py`) becomes the integration point — swap env-var fallback for Consul DNS or Linkerd local proxy
3. **Network segmentation** (`isli-public` / `isli-mesh` / `isli-data`) is already in place; the mesh overlays on `isli-mesh`
4. **Envoy sidecars** attach to `isli-mesh`; app containers use `network_mode: service:sidecar` and call `localhost:{sidecar_port}` for upstreams

### Original Full Plan

The complete Consul Connect design (control plane, sidecar pattern, intentions, Ollama mTLS, health check unification) is preserved in the plan file:

> `/root/.claude/projects/-home-projects-ISLI-AI/plans/service-mesh-hardening.md`

### Key Files Already Mesh-Ready

| File | Purpose |
|------|---------|
| `isli-core/src/isli_core/discovery.py` | Swap env fallback for mesh DNS |
| `docker-compose.yml` networks | `isli-mesh` is the sidecar overlay network |
| `isli-core/src/isli_core/auth.py` | `X-Internal-Auth` becomes secondary claim; mTLS provides primary identity |
