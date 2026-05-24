# ADR-003: Object storage — Scaleway Object Storage

**Date**: 2026-04-27
**Status**: accepted

## Decision

Use Scaleway Object Storage for all static files: voice notes, photos, generated PDFs (invoices, budgets).

## Consequences

- S3-compatible API — use `boto3` (Python) with a custom endpoint, no vendor-specific SDK needed
- Endpoint: `s3.{region}.scw.cloud` (e.g. `s3.fr-par.scw.cloud`)
- Credentials: `SCW_ACCESS_KEY` + `SCW_SECRET_KEY` environment variables
- Buckets: one per environment (`noa-prod`, `noa-staging`)
- File paths: `/{contractor_id}/{entity_type}/{uuid}.{ext}` — e.g. `/abc-123/invoices/xyz-456.pdf`
- Pre-signed URLs for client-facing file access (invoices sent via bot link)
