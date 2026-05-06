# Noa Infrastructure

Terraform-managed infrastructure on **Scaleway** (region `fr-par`).

## Architecture

```
Internet
   │
   ▼
Load Balancer (LB-S, static IP)        ← production only
   │  HTTPS :443
   ▼
Serverless Container (noa-api)         ← FastAPI, min 1 / max 5 instances
   │
   ├── PostgreSQL 16 (RDB)             ← noa-{environment} instance
   │      ACL: LB IP + dev machine
   │
   └── Object Storage bucket           ← noa-{environment}
          invoices/, budgets/, voice/, photos/
          IAM key scoped to this bucket only

Container Registry (private)           ← noa-{environment}
VPC Private Network                    ← reserved for future private DB endpoint
```

State is stored in Scaleway Object Storage: `noa-tf-state` bucket, `fr-par`.

| Environment | State key | LB |
|---|---|---|
| production | `noa/terraform.tfstate` | yes |
| staging | `noa-staging/terraform.tfstate` | no |

---

## Prerequisites

- `terraform >= 1.7`
- `scw` CLI (Scaleway CLI)
- `docker` (for image builds)
- Scaleway credentials: `SCW_ACCESS_KEY` + `SCW_SECRET_KEY`

---

## First-time bootstrap

### 1. Create the tfvars file

```bash
cp infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars.production
# fill in all CHANGE_ME values
```

Required secrets:

| Variable | Source |
|---|---|
| `db_password` | Generate: `openssl rand -base64 32 \| tr -d '/+=' \| head -c 32` |
| `anthropic_api_key` | console.anthropic.com |
| `telegram_bot_token` | BotFather on Telegram |
| `telegram_webhook_secret` | Generate: `openssl rand -hex 32` |
| `openai_api_key` | platform.openai.com |
| `google_client_id` | Google Cloud Console → APIs & Services → Credentials |
| `google_client_secret` | Same |
| `google_redirect_uri` | `https://<your-domain>/calendar/oauth/callback` |

### 2. Export credentials and run setup

```bash
export SCW_ACCESS_KEY=<key>
export SCW_SECRET_KEY=<secret>

./infra/scripts/setup.sh production
```

`setup.sh` creates the state bucket (idempotent) and initialises Terraform with the correct backend.

### 3. Review the plan

```bash
cd infra/terraform
AWS_ACCESS_KEY_ID=$SCW_ACCESS_KEY AWS_SECRET_ACCESS_KEY=$SCW_SECRET_KEY \
  terraform plan -var-file=terraform.tfvars.production
```

### 4. Apply

```bash
./infra/scripts/infra.sh production
```

### 5. Run migrations

```bash
./infra/scripts/migrate.sh production
```

---

## Deploying a new image

Use this for code-only changes (no infrastructure changes). Builds, pushes, and updates the container.

```bash
export SCW_ACCESS_KEY=<key>
export SCW_SECRET_KEY=<secret>

./infra/scripts/deploy.sh production          # uses current git SHA
./infra/scripts/deploy.sh production a3f1c2d  # specific SHA
```

CI runs this automatically on merge to `main`.

---

## Infrastructure changes

Use this when Terraform config changes (new resource, variable, etc.).

```bash
./infra/scripts/infra.sh production
```

This runs `terraform apply` against all resources (not just the container). Review the plan output carefully before confirming.

---

## Switching between environments

The `.terraform/` directory can only point at one environment at a time. `setup.sh` handles the switch via `-reconfigure`:

```bash
# Switch to staging
export SCW_ACCESS_KEY=<key> SCW_SECRET_KEY=<secret>
./infra/scripts/setup.sh staging

# Switch back to production
./infra/scripts/setup.sh production
```

Each environment has its own `.tfbackend` file (`staging.tfbackend`, `production.tfbackend`) which `setup.sh` picks up automatically.

---

## Running migrations against a deployed environment

The machine running migrations must be in the DB ACL (see `database.tf`). The script reads `DATABASE_URL` from Terraform state automatically.

```bash
./infra/scripts/migrate.sh production            # upgrade to head
./infra/scripts/migrate.sh production downgrade -1
```

---

## Outputs

After applying, retrieve key values:

```bash
cd infra/terraform
AWS_ACCESS_KEY_ID=$SCW_ACCESS_KEY AWS_SECRET_ACCESS_KEY=$SCW_SECRET_KEY \
  terraform output

# Individual values
terraform output -raw container_url
terraform output -raw registry_endpoint
terraform output lb_ip
```

---

## Costs (approximate, fr-par)

| Resource | Monthly |
|---|---|
| RDB DB-DEV-S | ~€13 |
| Serverless Container (1 warm instance) | ~€3 |
| Load Balancer LB-S | ~€15 |
| Object Storage | ~€0 at early scale |
| Container Registry | ~€0 at early scale |
| **Total (production)** | **~€31/month** |

Staging has no load balancer (`enable_lb = false`) and costs ~€16/month.
