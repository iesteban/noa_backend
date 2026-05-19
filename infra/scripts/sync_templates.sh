#!/usr/bin/env bash
# Sync WhatsApp message templates with the Meta Graph API.
# Creates missing templates and updates changed ones, then polls until approved.
#
# Usage:
#   ./infra/scripts/sync_templates.sh <environment>
#
# Examples:
#   ./infra/scripts/sync_templates.sh staging
#   ./infra/scripts/sync_templates.sh production
#
# Source the matching .env.<environment> before running, or export
# WHATSAPP_ACCESS_TOKEN and WHATSAPP_BUSINESS_ACCOUNT_ID directly.
set -euo pipefail

ENVIRONMENT="${1:?Usage: $0 <environment>}"
REPO_ROOT="$(git rev-parse --show-toplevel)"
ENV_FILE="$REPO_ROOT/.env.$ENVIRONMENT"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a; source "$ENV_FILE"; set +a
fi

if [[ -z "${WHATSAPP_BUSINESS_ACCOUNT_ID:-}" ]]; then
  echo "WHATSAPP_BUSINESS_ACCOUNT_ID is not set — nothing to do."
  exit 0
fi

echo "==> Syncing WhatsApp templates ($ENVIRONMENT)..."
cd "$REPO_ROOT"
.venv/bin/python -m app.scripts.sync_wa_templates

echo "==> Template sync complete."
