# 12 — Scale-Out Production Topology

> **Last updated:** 2026-05-11

## Single-Machine Topology (Dev / Small Team)

```
┌─────────────────────────────────────────────┐
│  Docker Compose on single host                │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐     │
│  │Core API │  │ Keeper  │  │ Board   │     │
│  │   x1    │  │   x1    │  │   x1    │     │
│  └────┬────┘  └────┬────┘  └─────────┘     │
│       │            │                         │
│  ┌────┴────────────┴────┐                   │
│  │  PostgreSQL + Redis   │                   │
│  │  (single instances)   │                   │
│  └───────────────────────┘                   │
└─────────────────────────────────────────────┘
```

## Scale-Out Topology (Production)

```
                    ┌─────────────┐
                    │   Traefik   │
                    │   (LB)      │
                    └──────┬──────┘
                           │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
      ┌─────────┐    ┌─────────┐    ┌─────────┐
      │Core API │    │Core API │    │Core API │
      │   x1    │    │   x2    │    │   x3    │
      └────┬────┘    └────┬────┘    └────┬────┘
           │               │               │
           └───────────────┼───────────────┘
                           ▼
              ┌────────────────────┐
              │  Redis Sentinel    │
              │  (3-node cluster)  │
              └────────────────────┘
                           ▼
              ┌────────────────────┐
              │  PostgreSQL HA     │
              │  (primary-replica) │
              └────────────────────┘
                           ▼
              ┌────────────────────┐
              │  ChromaDB Server   │
              │  (standalone)      │
              └────────────────────┘
```

## Scaling Principles

1. **Core API is stateless** — all state in PostgreSQL + Redis. Any instance can handle any request.
2. **WebSocket sessions** — sticky sessions via Traefik `cookie` LB or shared Redis pub/sub for broadcasts.
3. **Keeper** — one per Core API instance (sidecar) or shared pool behind internal LB.
4. **Ollama** — replica set with round-robin or GPU-aware scheduling.
5. **Skills** — independently scalable microservices; Core API routes via service discovery.

## Environment Variables (Production)

```env
# Load balancer
TRAEFIK_ENTRYPOINTS_WEB_ADDRESS=:80
TRAEFIK_ENTRYPOINTS_WEBSECURE_ADDRESS=:443
TRAEFIK_CERTIFICATESRESOLVERS_LETSENCRYPT_ACME_EMAIL=admin@example.com

# Redis Sentinel
REDIS_SENTINEL_HOSTS=sentinel-1:26379,sentinel-2:26379,sentinel-3:26379
REDIS_SENTINEL_MASTER=mymaster

# PostgreSQL HA
DATABASE_URL=postgresql+asyncpg://isli:password@pgbouncer:6432/isli
```
