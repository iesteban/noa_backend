#!/usr/bin/env bash
# First-time infrastructure bootstrap.
#
# Run this once before the first deploy. It:
#   1. Creates the Terraform state bucket in Scaleway Object Storage.
#   2. Initialises Terraform with the remote backend.
#   3. Runs terraform plan so you can review before applying.
#
# Requires: scw CLI authenticated, terraform >= 1.7, aws CLI (for s3 backend init).
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
TERRAFORM_DIR="$REPO_ROOT/infra/terraform"

STATE_BUCKET="noa-terraform-state"
REGION="fr-par"

echo "==> Creating Terraform state bucket (idempotent)..."
scw object bucket create \
  --name "$STATE_BUCKET" \
  --region "$REGION" 2>/dev/null || echo "    Bucket already exists, continuing."

echo "==> Initialising Terraform..."
cd "$TERRAFORM_DIR"

# The S3 backend needs AWS-style credentials pointing to Scaleway.
# Export SCW_ACCESS_KEY / SCW_SECRET_KEY from your environment or scw config.
AWS_ACCESS_KEY_ID="${SCW_ACCESS_KEY:-$(scw config get access-key)}" \
AWS_SECRET_ACCESS_KEY="${SCW_SECRET_KEY:-$(scw config get secret-key)}" \
terraform init \
  -backend-config="access_key=${SCW_ACCESS_KEY:-$(scw config get access-key)}" \
  -backend-config="secret_key=${SCW_SECRET_KEY:-$(scw config get secret-key)}"

echo ""
echo "==> Terraform initialised. Copy and fill in variables:"
echo "    cp $TERRAFORM_DIR/terraform.tfvars.example $TERRAFORM_DIR/terraform.tfvars"
echo ""
echo "    Then review the plan:"
echo "    cd $TERRAFORM_DIR && terraform plan"
echo ""
echo "    And apply:"
echo "    cd $TERRAFORM_DIR && terraform apply"
