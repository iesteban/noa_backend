#!/usr/bin/env bash
# Run Alembic migrations against a deployed database.
#
# Usage:
#   ./infra/scripts/migrate.sh <environment> [upgrade|downgrade] [revision]
#
# Examples:
#   ./infra/scripts/migrate.sh staging
#   ./infra/scripts/migrate.sh production downgrade -1
#
# Reads DATABASE_URL from Terraform outputs.
# The machine running this script must be allowed through the DB ACL (see database.tf).
set -euo pipefail

ENVIRONMENT="${1:?Usage: $0 <environment> [upgrade|downgrade] [revision]}"
COMMAND="${2:-upgrade}"
REVISION="${3:-head}"

REPO_ROOT="$(git rev-parse --show-toplevel)"
TERRAFORM_DIR="$REPO_ROOT/infra/terraform"

echo "==> Reading DATABASE_URL from Terraform state ($ENVIRONMENT)..."
cd "$TERRAFORM_DIR"
export DATABASE_URL="$(AWS_ACCESS_KEY_ID=$SCW_ACCESS_KEY AWS_SECRET_ACCESS_KEY=$SCW_SECRET_KEY terraform output -raw database_url)"

echo "==> Running: alembic $COMMAND $REVISION"
cd "$REPO_ROOT"
.venv/bin/alembic "$COMMAND" "$REVISION"

echo "==> Migration complete."
