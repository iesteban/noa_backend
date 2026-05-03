#!/usr/bin/env bash
# Deploy a new version of the Noa API.
#
# Usage:
#   ./infra/scripts/deploy.sh <environment> [image_tag]
#
# Examples:
#   ./infra/scripts/deploy.sh staging
#   ./infra/scripts/deploy.sh production a3f1c2d
#
# image_tag defaults to the current git SHA (short).
# Source the matching .env.<environment> before running.
set -euo pipefail

ENVIRONMENT="${1:?Usage: $0 <environment> [image_tag]}"
IMAGE_TAG="${2:-$(git rev-parse --short HEAD)}"

REPO_ROOT="$(git rev-parse --show-toplevel)"
TERRAFORM_DIR="$REPO_ROOT/infra/terraform"
TFVARS="$TERRAFORM_DIR/terraform.tfvars.$ENVIRONMENT"

if [[ ! -f "$TFVARS" ]]; then
  echo "Error: $TFVARS not found."
  exit 1
fi

echo "==> Resolving registry endpoint from Terraform state..."
cd "$TERRAFORM_DIR"
REGISTRY_ENDPOINT="$(AWS_ACCESS_KEY_ID=$SCW_ACCESS_KEY AWS_SECRET_ACCESS_KEY=$SCW_SECRET_KEY terraform output -raw registry_endpoint)"

IMAGE="$REGISTRY_ENDPOINT/noa-api:$IMAGE_TAG"

echo "==> Authenticating with Scaleway Container Registry..."
docker login "$REGISTRY_ENDPOINT" -u nologin -p "$SCW_SECRET_KEY"

echo "==> Building image $IMAGE..."
docker build \
  --platform linux/amd64 \
  --tag "$IMAGE" \
  "$REPO_ROOT"

echo "==> Pushing image to registry..."
docker push "$IMAGE"

echo "==> Updating Terraform with new image tag: $IMAGE_TAG..."
AWS_ACCESS_KEY_ID=$SCW_ACCESS_KEY AWS_SECRET_ACCESS_KEY=$SCW_SECRET_KEY \
terraform apply \
  -var-file="$TFVARS" \
  -var "image_tag=$IMAGE_TAG" \
  -auto-approve

echo ""
echo "==> Deploy complete."
echo "    Container URL: $(AWS_ACCESS_KEY_ID=$SCW_ACCESS_KEY AWS_SECRET_ACCESS_KEY=$SCW_SECRET_KEY terraform output -raw container_url)"
