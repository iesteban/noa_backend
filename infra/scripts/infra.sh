#!/usr/bin/env bash
# Apply infrastructure changes (DB, VPC, registry, container, storage).
# Run this when Terraform config changes, not on every code deploy.
#
# Usage:
#   ./infra/scripts/infra.sh <environment> [image_tag]
#
# Examples:
#   ./infra/scripts/infra.sh staging
#   ./infra/scripts/infra.sh production
#
# image_tag defaults to the currently deployed tag from Terraform state, so infra
# changes never accidentally update the running image to an unpushed SHA.
# Pass an explicit tag as the second argument to override (e.g. first deploy).
# Source the matching .env.<environment> before running.
set -euo pipefail

ENVIRONMENT="${1:?Usage: $0 <environment> [image_tag]}"

REPO_ROOT="$(git rev-parse --show-toplevel)"
TERRAFORM_DIR="$REPO_ROOT/infra/terraform"
TFVARS="$TERRAFORM_DIR/terraform.tfvars.$ENVIRONMENT"

if [[ ! -f "$TFVARS" ]]; then
  echo "Error: $TFVARS not found."
  exit 1
fi

echo "==> Applying full infrastructure for environment: $ENVIRONMENT..."
cd "$TERRAFORM_DIR"

# Use the currently deployed image tag from state so infra changes don't accidentally
# point the container at an unpushed SHA. Fall back to current git SHA on first deploy.
DEPLOYED_TAG=$(AWS_ACCESS_KEY_ID=$SCW_ACCESS_KEY AWS_SECRET_ACCESS_KEY=$SCW_SECRET_KEY \
  terraform output -raw image_tag 2>/dev/null || true)
IMAGE_TAG="${2:-${DEPLOYED_TAG:-$(git rev-parse --short HEAD)}}"
echo "    image_tag: $IMAGE_TAG"

AWS_ACCESS_KEY_ID=$SCW_ACCESS_KEY AWS_SECRET_ACCESS_KEY=$SCW_SECRET_KEY \
terraform apply \
  -var-file="$TFVARS" \
  -var "image_tag=$IMAGE_TAG" \
  -auto-approve

echo ""
echo "==> Infrastructure apply complete."
echo "    Container URL: $(AWS_ACCESS_KEY_ID=$SCW_ACCESS_KEY AWS_SECRET_ACCESS_KEY=$SCW_SECRET_KEY terraform output -raw container_url 2>/dev/null || echo '(run terraform output -raw container_url to see it)')"
