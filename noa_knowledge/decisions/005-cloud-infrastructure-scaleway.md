# ADR-005: Cloud infrastructure — Scaleway (database + API hosting)

**Date**: 2026-05-02  
**Status**: accepted

## Context

Noa needs a European cloud provider for managed PostgreSQL and API hosting. Object storage is already on Scaleway (ADR-003). The options evaluated were:

| Provider | Managed Postgres | Container hosting | Object storage | Pricing | DX |
|----------|-----------------|-------------------|----------------|---------|----|
| Scaleway | ✓ | Serverless Containers | ✓ (already using) | Mid | Good |
| Hetzner | ✓ | VMs only | ✓ | Cheapest | Basic |
| OVHcloud | ✓ | Managed Kubernetes | ✓ | Mid | Poor |

All three are GDPR-compliant and EU-headquartered. Fly.io was excluded — US-headquartered despite having EU regions.

Hetzner is 40–60% cheaper on compute and Postgres, but has no managed container runtime — the API would run on a bare VM, requiring self-managed deployment tooling (Coolify, Dokku, or similar).

## Decision

Host the API and database on **Scaleway**, co-located with the existing object storage bucket in `fr-par` (Paris).

- **Database**: Scaleway Managed PostgreSQL (`fr-par`)
- **API**: Scaleway Serverless Containers (`fr-par`)
- **Storage**: Scaleway Object Storage (`fr-par`) — existing, per ADR-003
- **IaC**: Terraform with the official `scaleway/scaleway` provider

Keeping all three services in one provider and one region eliminates cross-provider networking, simplifies IAM, and means a single Terraform config manages the full infrastructure.

## Consequences

**Easier:**
- No egress fees between the API, database, and object storage (same region)
- One provider account, one billing dashboard, one Terraform provider
- Scaleway Serverless Containers scales to zero — cheap for the early phase with low traffic
- Official Terraform provider covers Postgres, Serverless Containers, and Object Storage

**Harder:**
- Scaleway is smaller than OVH — fewer advanced managed services if needs grow (e.g. managed Redis, managed Kafka)
- If cost becomes a constraint at scale, migrating compute and DB to Hetzner is the most likely exit path — Terraform abstracts most of it, but connection strings and networking will need updating
- Serverless Containers has a cold-start latency (~200–500ms) — acceptable for a messaging bot where the WhatsApp/Telegram platform already adds latency, but worth monitoring
