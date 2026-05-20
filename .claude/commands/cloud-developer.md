# Noa Cloud — Infrastructure & Deploy Guide

Everything runs on Scaleway (`fr-par`). Terraform manages all resources. Two environments: **staging** (no load balancer, ~€16/month) and **production** (LB enabled, ~€31/month).

---

## Infrastructure map

| Resource | Terraform file | Notes |
|---|---|---|
| Scaleway Serverless Container | `containers.tf` | FastAPI app, 1–5 replicas |
| Container Registry | `registry.tf` | One namespace per env (`noa-staging`, `noa-production`) |
| PostgreSQL 16 (RDB) | `database.tf` | `DB-DEV-S`, auto-growing volume |
| Redis 8.6.3 (cluster) | `redis.tf` | `RED1-MICRO`, TLS, public network |
| Object Storage bucket | `storage.tf` | `noa-staging` / `noa-production` |
| VPC / private network | `network.tf` | |
| Load balancer (prod only) | `loadbalancer.tf` | Controlled by `var.enable_lb` |
| Cloudflare DNS | `dns.tf` | `api-staging.botnoa.com` / `api.botnoa.com` |
| Terraform state bucket | manual (S3) | `noa-tf-state` in Scaleway Object Storage |

---

## Terraform state

State lives in `noa-tf-state` (Scaleway S3-compatible). Two separate state keys, one per environment — switching requires re-init:

```bash
# Switch to staging state
cd infra/terraform
AWS_ACCESS_KEY_ID=$SCW_ACCESS_KEY AWS_SECRET_ACCESS_KEY=$SCW_SECRET_KEY \
  terraform init -reconfigure -backend-config=staging.tfbackend

# Switch to production state
AWS_ACCESS_KEY_ID=$SCW_ACCESS_KEY AWS_SECRET_ACCESS_KEY=$SCW_SECRET_KEY \
  terraform init -reconfigure -backend-config=production.tfbackend
```

Always source the matching env file before running Terraform to export credentials:

```bash
set -a && source .env.staging && set +a      # or .env.production
```

---

## Secret management — strict rule

**Every secret lives in exactly two places: `.env.<env>` (local) and GitHub Actions secrets (CI). Nowhere else.**

- `.env.staging` / `.env.production` — gitignored, local source of truth
- `infra/terraform/terraform.tfvars.*` — gitignored, non-secret config only (`environment`, `enable_lb`, `api_domain`, `redis_node_type`, `db_node_type`)
- Terraform gets secrets via `TF_VAR_*` env vars — locally sourced from `.env.*`, in CI from GitHub secrets
- GitHub secret naming: `STAGING_<VAR>` / `PRODUCTION_<VAR>` (e.g. `STAGING_REDIS_PASSWORD`)
- When adding a new secret use `/add-secret` — it wires all 8 locations automatically

---

## Local apply — when to use infra scripts

| Script | What it does | When to use |
|---|---|---|
| `infra/scripts/setup.sh <env>` | Creates state bucket, runs `terraform init` | First deploy or switching environments |
| `infra/scripts/infra.sh <env>` | Full `terraform apply` | Terraform config changed (new resource, variable, etc.) |
| `infra/scripts/deploy.sh <env> [sha]` | Build + push image, update container only | Code-only deploy with no infra changes |
| `infra/scripts/migrate.sh <env>` | Run Alembic migrations against deployed DB | After every deploy that includes migrations |

```bash
source .env.staging          # export credentials
./infra/scripts/infra.sh staging
./infra/scripts/migrate.sh staging
```

### Cloudflare token expiry

The Cloudflare token in `.env.staging` has expired previously and blocks full `terraform apply` with an auth error. If this happens, use `-target` to apply only the resources you need and skip the DNS resources:

```bash
AWS_ACCESS_KEY_ID=$SCW_ACCESS_KEY AWS_SECRET_ACCESS_KEY=$SCW_SECRET_KEY \
  terraform apply \
    -target=scaleway_redis_cluster.main \
    -target=scaleway_container.api \
    -var-file=terraform.tfvars.staging \
    -var "image_tag=<sha>" \
    -auto-approve
```

---

## GitHub CI workflows

### `ci.yml` — runs on every push and PR

| Job | Trigger | What it does |
|---|---|---|
| `lint-and-test` | every push / PR | ruff, mypy, unit tests, migrations, integration tests |
| `deploy-staging` | push to `main` only | builds image → pushes to SCW registry → `terraform apply -target=scaleway_container.api` → `alembic upgrade head` |

The staging deploy uses `-target=scaleway_container.api -target=scaleway_container_domain.api -target=cloudflare_record.api` — it only updates the running container, not the full infra. Infra changes (new Terraform resources) require a manual `infra.sh` run locally.

### `deploy-production.yml` — manual dispatch only

Triggered via GitHub Actions UI (`workflow_dispatch`). Accepts an optional `sha` input (defaults to latest `main`). Builds, pushes, applies, migrates — same pattern as staging.

**To deploy to production:**
```
GitHub → Actions → Deploy to production → Run workflow → (optionally specify SHA)
```

---

## Adding a new Terraform resource

1. Create or edit the relevant `.tf` file in `infra/terraform/`
2. If it needs a new non-secret variable, add it to `variables.tf` with a `default`; add it to `terraform.tfvars.example` and both `terraform.tfvars.*` files
3. If it needs a new secret variable, use `/add-secret` instead
4. If the resource needs to be available before the container starts, add it to `depends_on` in `containers.tf`
5. If its outputs are needed (e.g. a URL or host), add them to `outputs.tf` and construct the env var in `containers.tf` locals
6. Apply locally with `infra.sh` — CI only updates the container, not new resources

### Example: how Redis was added

- `redis.tf` — `scaleway_redis_cluster` resource
- `variables.tf` — `redis_node_type` (non-secret, default `RED1-MICRO`) + `redis_password` (sensitive)
- `containers.tf` — `local.redis_url` constructed from cluster outputs, passed as `REDIS_URL` secret env var
- `outputs.tf` — `redis_host`, `redis_port`
- `app/config.py` — `redis_url: str` setting
- `app/redis.py` — `get_redis()` lazy client singleton

---

## Redis

- Version: **8.6.3** (only version available on Scaleway `fr-par-1` as of 2026-05)
- Node type: `RED1-MICRO`
- TLS enabled → use `rediss://` scheme (not `redis://`)
- Auth: username `noa` + password from `REDIS_PASSWORD`
- Staging endpoint: `51.15.222.22:6379`
- Production endpoint: `163.172.136.10:6379`
- Full URLs are in `.env.staging` / `.env.production` as `REDIS_URL`

Local dev uses plain Redis 7 Alpine via docker-compose (`redis://localhost:6379/0`).

---

## CI integration test environment

The `lint-and-test` job runs with dummy secrets (`dummy` strings for all API keys). It spins up a real Postgres 16 container as a service. There is no Redis service in CI — integration tests must not depend on Redis, or the CI job must be updated to add a Redis service alongside Postgres.

---

## Gotchas

- **Re-init required when switching environments.** `terraform init -reconfigure -backend-config=<env>.tfbackend`. Forgetting this applies staging config to production state.
- **CI only deploys the container.** New Terraform resources (DB changes, new buckets, Redis) must be applied locally with `infra.sh` before the CI deploy will work.
- **Scaleway Redis version.** Only `8.6.3` is available in `fr-par-1`. Don't change the `version` field in `redis.tf` without checking `scw redis version list zone=fr-par-1`.
- **Cloudflare token.** Separate from Scaleway credentials. Stored as `CLOUDFLARE_API_TOKEN` in env files and as `CLOUDFLARE_API_TOKEN` (no env prefix) in GitHub secrets. Expires — renew in CF dashboard if full `terraform apply` fails with auth error 10000.
- **Image tag drift.** When running manual targeted applies, always extract the current deployed SHA from state (`terraform state show scaleway_container.api | grep registry_image`) before passing `-var image_tag=`. Never fall back to `git rev-parse HEAD` unless you've verified that SHA exists in the registry.
