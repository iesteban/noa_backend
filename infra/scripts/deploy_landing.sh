#!/usr/bin/env bash
# Sync the landing/ directory to the noa-www S3 bucket.
#
# Usage:
#   source .env.production
#   ./infra/scripts/deploy_landing.sh
#
# Requires: aws CLI, SCW_ACCESS_KEY and SCW_SECRET_KEY in the environment.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
BUCKET="noa-www"
ENDPOINT="https://s3.fr-par.scw.cloud"
REGION="fr-par"

if [[ -z "${SCW_ACCESS_KEY:-}" || -z "${SCW_SECRET_KEY:-}" ]]; then
  echo "Error: SCW_ACCESS_KEY and SCW_SECRET_KEY must be set."
  echo "       Run: source .env.production"
  exit 1
fi

echo "==> Syncing landing/ to s3://$BUCKET/..."
AWS_ACCESS_KEY_ID=$SCW_ACCESS_KEY \
AWS_SECRET_ACCESS_KEY=$SCW_SECRET_KEY \
aws s3 sync "$REPO_ROOT/landing/" "s3://$BUCKET/" \
  --endpoint-url "$ENDPOINT" \
  --region "$REGION" \
  --delete \
  --acl public-read \
  --cache-control "max-age=3600, public"

echo ""
echo "==> Deploy complete."
echo "    URL: https://$BUCKET.s3-website.$REGION.scw.cloud"
