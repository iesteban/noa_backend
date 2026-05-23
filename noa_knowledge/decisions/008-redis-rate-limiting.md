# ADR-008: Redis for rate limiting

**Date**: 2026-05-10  
**Status**: accepted

## Context

Noa needs rate limiting across four dimensions to control costs and prevent abuse:

- **Bot messages** — per-contractor hourly and daily caps to prevent runaway usage
- **AI calls** — per-contractor daily caps on Whisper transcriptions and Claude API calls (direct cost control)
- **Document generation** — monthly caps on invoices and budgets (business model lever)
- **HTTP endpoints** — request-per-minute caps on webhook endpoints to prevent API abuse

PostgreSQL could store counters, but rate limiting is a read-modify-write hot path hit on every bot message. Doing this in Postgres adds query latency and write load to the primary database on every interaction.

Redis is the standard tool for this: `INCR` is atomic, keys have native TTL (no cleanup jobs needed), and latency is sub-millisecond.

## Decision

Add a **Scaleway Managed Redis cluster** (`fr-par`, same region as Postgres and object storage) for rate limiting.

- **Cluster**: `scaleway_redis_cluster`, node type `RED1-XS` (smallest — sufficient for early stage), single node, TLS enabled
- **Client**: `redis-py` v4+ async interface (`redis.asyncio`) — consistent with FastAPI's async model
- **HTTP rate limiting**: `fastapi-limiter` (native async, decorator-based, backed by the same Redis instance)
- **Key format**: `rate:{contractor_id}:{resource}:{window_key}` — e.g. `rate:abc123:whisper:2026-05-10`
- **Limits**: configurable via ENV vars with safe defaults

Keeping Redis in Scaleway (`fr-par`) avoids cross-provider networking and stays within the existing Terraform config.

## Consequences

**Easier:**
- Rate limit checks add <1ms latency — no Postgres round-trip on every message
- TTL on keys means no cleanup job — counters expire automatically when the window closes
- `fastapi-limiter` handles HTTP-level limits with a single decorator — minimal boilerplate
- Single Redis instance serves all four rate limit types
- Scaleway co-location means no egress fees between Redis and the API container

**Harder:**
- New managed service to operate (monitor, patch, backup) — mitigated by Scaleway managing it
- Redis is not persistent by default — a Redis restart resets counters mid-window. Acceptable: brief over-counting is better than blocking legitimate users
- Adds a startup dependency: the API must connect to Redis on boot. Health check must include Redis ping
