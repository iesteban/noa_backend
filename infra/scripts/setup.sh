#!/usr/bin/env bash
# First-time infrastructure bootstrap.
#
# Usage:
#   ./infra/scripts/setup.sh <environment>
#
# Examples:
#   ./infra/scripts/setup.sh staging
#   ./infra/scripts/setup.sh production
#
# Requires: scw CLI, terraform >= 1.7.
# Source the matching .env.<environment> before running.
set -euo pipefail

ENVIRONMENT="${1:?Usage: $0 <environment>}"

REPO_ROOT="$(git rev-parse --show-toplevel)"
TERRAFORM_DIR="$REPO_ROOT/infra/terraform"
TFVARS="$TERRAFORM_DIR/terraform.tfvars.$ENVIRONMENT"

if [[ ! -f "$TFVARS" ]]; then
  echo "Error: $TFVARS not found. Copy terraform.tfvars.example and fill in values."
  exit 1
fi

STATE_BUCKET="noa-terraform-state"
REGION="fr-par"

echo "==> Creating Terraform state bucket (idempotent)..."
scw object bucket create \
  --name "$STATE_BUCKET" \
  --region "$REGION" 2>/dev/null || echo "    Bucket already exists, continuing."

echo "==> Initialising Terraform..."
cd "$TERRAFORM_DIR"

AWS_ACCESS_KEY_ID="${SCW_ACCESS_KEY:-$(scw config get access-key)}" \
AWS_SECRET_ACCESS_KEY="${SCW_SECRET_KEY:-$(scw config get secret-key)}" \
terraform init \
  -backend-config="access_key=${SCW_ACCESS_KEY:-$(scw config get access-key)}" \
  -backend-config="secret_key=${SCW_SECRET_KEY:-$(scw config get secret-key)}"

echo ""
echo "==> Terraform initialised. Review the plan:"
echo "    cd $TERRAFORM_DIR && terraform plan -var-file=terraform.tfvars.$ENVIRONMENT"
echo ""
echo "    Then apply:"
echo "    cd $TERRAFORM_DIR && terraform apply -var-file=terraform.tfvars.$ENVIRONMENT"
