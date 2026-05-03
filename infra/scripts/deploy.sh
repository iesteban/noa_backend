#!/usr/bin/env bash
# Deploy a new version of the Noa API.
#
# Usage:
#   ./infra/scripts/deploy.sh [IMAGE_TAG]
#
# IMAGE_TAG defaults to the current git SHA (short).
# Requires: docker, terraform, scw CLI authenticated.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
TERRAFORM_DIR="$REPO_ROOT/infra/terraform"

IMAGE_TAG="${1:-$(git rev-parse --short HEAD)}"

echo "==> Resolving registry endpoint from Terraform state..."
cd "$TERRAFORM_DIR"
REGISTRY_ENDPOINT="$(terraform output -raw registry_endpoint)"

IMAGE="$REGISTRY_ENDPOINT/noa-api:$IMAGE_TAG"

echo "==> Authenticating with Scaleway Container Registry..."
scw container namespace list | head -1 > /dev/null  # ensures scw CLI is authed
docker login "$REGISTRY_ENDPOINT" \
  -u nologin \
  --password-stdin <<< "$(scw iam api-key get | grep 'SecretKey' | awk '{print $2}')" 2>/dev/null || \
  docker login "$REGISTRY_ENDPOINT" -u nologin -p "$(scw config get secret-key)"

echo "==> Building image $IMAGE..."
docker build \
  --platform linux/amd64 \
  --tag "$IMAGE" \
  "$REPO_ROOT"

echo "==> Pushing image to registry..."
docker push "$IMAGE"

echo "==> Updating Terraform with new image tag: $IMAGE_TAG..."
terraform apply \
  -var "image_tag=$IMAGE_TAG" \
  -auto-approve

echo ""
echo "==> Deploy complete."
echo "    Container URL : $(terraform output -raw container_url)"
echo "    LB IP         : $(terraform output -raw lb_ip)"
