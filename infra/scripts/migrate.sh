#!/usr/bin/env bash
# Run Alembic migrations against the production database.
#
# Usage:
#   ./infra/scripts/migrate.sh [upgrade|downgrade] [revision]
#
# Examples:
#   ./infra/scripts/migrate.sh              # upgrade head
#   ./infra/scripts/migrate.sh downgrade -1
#
# Reads DATABASE_URL from Terraform outputs. The machine running this script
# must be allowed through the DB ACL (see database.tf acl_rules).
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
TERRAFORM_DIR="$REPO_ROOT/infra/terraform"

COMMAND="${1:-upgrade}"
REVISION="${2:-head}"

echo "==> Reading DATABASE_URL from Terraform state..."
cd "$TERRAFORM_DIR"
export DATABASE_URL="$(terraform output -raw database_url)"

echo "==> Running: alembic $COMMAND $REVISION"
cd "$REPO_ROOT"
alembic "$COMMAND" "$REVISION"

echo "==> Migration complete."
